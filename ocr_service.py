"""
Модуль работы с OCR.space API.

Отправляет изображения и PDF файлы на распознавание текста.
Поддерживает отправку через base64 (фото) и multipart (PDF).
"""

import base64
import logging
import requests

from config import OCR_API_KEY, OCR_API_URL, OCR_LANGUAGE, OCR_ENGINE

logger = logging.getLogger(__name__)


def ocr_from_file(file_path: str) -> dict:
    """
    Отправляет файл (изображение или PDF) на OCR.space API.

    Args:
        file_path: Путь к файлу (jpg, png, pdf).

    Returns:
        dict с ключами:
            - success (bool): успешность распознавания
            - text (str): извлечённый текст
            - error (str | None): сообщение об ошибке
    """
    try:
        # Определяем тип файла
        ext = file_path.lower().rsplit(".", 1)[-1] if "." in file_path else ""
        is_pdf = ext == "pdf"

        if is_pdf:
            return _ocr_multipart(file_path)
        else:
            return _ocr_base64(file_path)

    except Exception as e:
        logger.error(f"Ошибка OCR: {e}")
        return {"success": False, "text": "", "error": str(e)}


def ocr_from_bytes(file_bytes: bytes, filename: str = "image.jpg") -> dict:
    """
    Отправляет байты файла на OCR.space API.

    Args:
        file_bytes: Содержимое файла в байтах.
        filename: Имя файла (для определения типа).

    Returns:
        dict с ключами: success, text, error.
    """
    try:
        ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else "jpg"
        is_pdf = ext == "pdf"

        if is_pdf:
            return _ocr_multipart_bytes(file_bytes, filename)
        else:
            return _ocr_base64_bytes(file_bytes, ext)

    except Exception as e:
        logger.error(f"Ошибка OCR: {e}")
        return {"success": False, "text": "", "error": str(e)}


def _ocr_base64(file_path: str) -> dict:
    """Отправка изображения через base64."""
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    ext = file_path.lower().rsplit(".", 1)[-1]
    return _ocr_base64_bytes(file_bytes, ext)


def _ocr_base64_bytes(file_bytes: bytes, ext: str = "jpg") -> dict:
    """Отправка изображения (байты) через base64."""
    mime_types = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "bmp": "image/bmp",
        "tif": "image/tiff",
        "tiff": "image/tiff",
    }
    mime = mime_types.get(ext, "image/jpeg")

    encoded = base64.b64encode(file_bytes).decode("utf-8")
    base64_string = f"data:{mime};base64,{encoded}"

    payload = {
        "base64Image": base64_string,
        "language": OCR_LANGUAGE,
        "isTable": True,
        "scale": True,
        "OCREngine": OCR_ENGINE,
        "detectOrientation": True,
    }

    headers = {"apikey": OCR_API_KEY}

    logger.info(f"Отправка изображения на OCR.space (base64, {len(file_bytes)} байт)")
    response = requests.post(OCR_API_URL, data=payload, headers=headers, timeout=120)
    return _parse_response(response)


def _ocr_multipart(file_path: str) -> dict:
    """Отправка PDF через multipart upload."""
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    filename = file_path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
    return _ocr_multipart_bytes(file_bytes, filename)


def _ocr_multipart_bytes(file_bytes: bytes, filename: str) -> dict:
    """Отправка PDF (байты) через multipart upload."""
    payload = {
        "language": OCR_LANGUAGE,
        "isTable": True,
        "scale": True,
        "OCREngine": OCR_ENGINE,
        "detectOrientation": True,
        "filetype": "PDF",
    }

    headers = {"apikey": OCR_API_KEY}
    files = {"file": (filename, file_bytes, "application/pdf")}

    logger.info(f"Отправка PDF на OCR.space (multipart, {len(file_bytes)} байт)")
    response = requests.post(
        OCR_API_URL, data=payload, headers=headers, files=files, timeout=120
    )
    return _parse_response(response)


def _parse_response(response: requests.Response) -> dict:
    """Парсит ответ OCR.space API."""
    if response.status_code != 200:
        return {
            "success": False,
            "text": "",
            "error": f"HTTP ошибка: {response.status_code}",
        }

    result = response.json()

    # Проверяем ошибки API
    if result.get("IsErroredOnProcessing", False):
        error_msg = result.get("ErrorMessage", ["Неизвестная ошибка"])
        if isinstance(error_msg, list):
            error_msg = "; ".join(error_msg)
        return {"success": False, "text": "", "error": error_msg}

    exit_code = result.get("OCRExitCode", 0)
    if exit_code not in (1, 2):  # 1 = полный успех, 2 = частичный успех
        return {
            "success": False,
            "text": "",
            "error": f"OCR завершился с кодом {exit_code}",
        }

    # Собираем текст со всех страниц
    parsed_results = result.get("ParsedResults", [])
    all_text = []
    for page in parsed_results:
        text = page.get("ParsedText", "")
        if text:
            all_text.append(text.strip())

    combined_text = "\n".join(all_text)

    if not combined_text:
        return {
            "success": False,
            "text": "",
            "error": "OCR не обнаружил текст на изображении",
        }

    logger.info(f"OCR успешно: {len(combined_text)} символов извлечено")
    return {"success": True, "text": combined_text, "error": None}
