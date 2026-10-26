"""Offline container check with synthetic data; never calls a provider."""
import os
import tempfile
from io import BytesIO

from docx import Document
from pypdf import PdfReader

from app.auth import AUTH_REQUIRED, COOKIE_SECURE
from app.database import Base, DATA_DIR, engine
from app import models  # register schema
from app.document_pdf import docx_to_pdf


assert os.geteuid() != 0, 'Container must not run as root'
assert AUTH_REQUIRED and COOKIE_SECURE
Base.metadata.create_all(engine)
with tempfile.TemporaryFile(dir=DATA_DIR) as handle:
    handle.write(b'offline smoke')
document = Document()
document.add_paragraph('Curriculo sintetico — selecao')
buffer = BytesIO()
document.save(buffer)
pdf = docx_to_pdf(buffer.getvalue(), title='Auditoria')
assert len(PdfReader(BytesIO(pdf)).pages) == 1
print('Container: non-root, writable data, secure flags, schema and DOCX/PDF OK')
