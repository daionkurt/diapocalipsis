-- Para proyectos donde ya ejecutaste setup.sql. Conserva registros y archivos.
UPDATE storage.buckets
SET allowed_mime_types = ARRAY['application/pdf', 'application/octet-stream', 'application/vnd.openxmlformats-officedocument.presentationml.presentation', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/plain'],
    file_size_limit = GREATEST(file_size_limit, 52428800)
WHERE id = 'presentaciones';
