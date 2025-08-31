# ticketflow/validators.py
from django.core.exceptions import ValidationError

# Allowed MIME types (adjust if you need more)
ALLOWED_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    "application/msword",  # .doc
}
MAX_UPLOAD_MB = 5  # change if needed

def validate_uploaded_file(f):
    # Size check
    size_mb = (f.size or 0) / (1024 * 1024)
    if size_mb > MAX_UPLOAD_MB:
        raise ValidationError(f"File too large ({size_mb:.1f} MB). Max {MAX_UPLOAD_MB} MB")

    # Content type check (some storages may not set this)
    content_type = getattr(f, "content_type", "") or ""
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        raise ValidationError("Unsupported file type.")