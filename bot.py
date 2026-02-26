import os
import io
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import fitz  # PyMuPDF
import cv2
import numpy as np
from PIL import Image

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Config
TOKEN = os.environ.get('TOKEN')  # Heroku config var se milega
PORT = int(os.environ.get('PORT', '8443'))  # Heroku PORT env var

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "PDF bhejo watermark wala → main clean kar ke wapas bhej dunga! 🚀\n"
        "(Sirf personal/study use ke liye)"
    )

async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    document = update.message.document
    if not document or not document.file_name.lower().endswith('.pdf'):
        await update.message.reply_text("Sirf PDF file bhejo!")
        return

    await update.message.reply_text("PDF process ho raha hai... thoda time lagega (pages ke hisaab se)")

    try:
        file = await document.get_file()
        pdf_bytes = await file.download_as_bytearray()

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        new_doc = fitz.open()

        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=120)  # balance quality & speed

            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

            # Red watermark mask (adjust HSV if different color)
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            lower_red1 = np.array([0, 70, 70])
            upper_red1 = np.array([10, 255, 255])
            lower_red2 = np.array([160, 70, 70])
            upper_red2 = np.array([180, 255, 255])
            mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
            mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
            mask = cv2.bitwise_or(mask1, mask2)

            # Dilate to cover full text/logo
            kernel = np.ones((3, 3), np.uint8)
            mask = cv2.dilate(mask, kernel, iterations=1)

            # Inpaint remove
            cleaned = cv2.inpaint(img, mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)

            # Back to fitz Pixmap
            cleaned_rgb = cv2.cvtColor(cleaned, cv2.COLOR_BGR2RGB)
            cleaned_pil = Image.fromarray(cleaned_rgb)
            cleaned_pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, pix.w, pix.h), False)
            cleaned_pix.set_pixel_bytes(cleaned_pil.tobytes("raw", "RGB"))

            # New clean page
            new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(new_page.rect, pixmap=cleaned_pix)

        # Output bytes
        output = io.BytesIO()
        new_doc.save(output, garbage=4, deflate=True)
        output.seek(0)

        await update.message.reply_document(
            document=output,
            filename=f"clean_{document.file_name}",
            caption="Watermark hat gaya! Enjoy 🔥"
        )

    except Exception as e:
        logger.error(f"Error processing PDF: {e}")
        await update.message.reply_text("Kuch error aaya... PDF bhej do fir se ya simple file try karo.")

    finally:
        if 'doc' in locals():
            doc.close()
        if 'new_doc' in locals():
            new_doc.close()

def main() -> None:
    if not TOKEN:
        logger.error("TOKEN environment variable not set!")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))

    # Webhook setup for Heroku
    webhook_url = f"https://{os.environ.get('HEROKU_APP_NAME', 'your-app-name')}.herokuapp.com/{TOKEN}"
    
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=webhook_url,
        # Optional: drop_pending_updates=True if you want to ignore old messages
    )

if __name__ == '__main__':
    main()
