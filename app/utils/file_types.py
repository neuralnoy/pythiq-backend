SUPPORTED_MIME_TYPES = {
    # Base types
    'application/pdf',
    
    # Documents and presentations
    'application/x-t602',
    'application/x-abiword',
    'image/cgm',
    'application/x-appleworks-document',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-word.document.macroEnabled.12',
    'application/vnd.ms-word.template.macroEnabled.12',
    'application/x-hwp',
    'application/x-iwork-keynote-sffkey',
    'application/vnd.lotus-wordpro',
    'application/x-iwork-pages-sffpages',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'application/rtf',
    'text/plain',
    'application/xml',
    'application/epub+zip',
    
    # Images
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/bmp',
    'image/svg+xml',
    'image/tiff',
    'image/webp',
    'text/html',
    
    # Spreadsheets
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-excel',
    'application/vnd.ms-excel.sheet.macroEnabled.12',
    'application/vnd.ms-excel.sheet.binary.macroEnabled.12',
    'text/csv',
    'application/x-iwork-numbers-sffnumbers',
    'application/vnd.oasis.opendocument.spreadsheet',
    'text/tab-separated-values'
}

SUPPORTED_EXTENSIONS = {
    'pdf', '602', 'abw', 'cgm', 'cwk', 'doc', 'docx', 'docm', 'dot', 'dotm',
    'hwp', 'key', 'lwp', 'pages', 'ppt', 'pptm', 'pptx', 'pot', 'potm', 'potx',
    'rtf', 'txt', 'xml', 'epub', 'jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg',
    'tiff', 'webp', 'htm', 'html', 'xlsx', 'xls', 'xlsm', 'xlsb', 'csv',
    'numbers', 'ods', 'tsv'
}

def normalize_content_type(content_type: str, filename: str) -> str:
    """Normalize content type based on file extension if needed"""
    extension = filename.lower().split('.')[-1] if '.' in filename else ''
    
    # Map of extensions to content types that might need normalization
    content_type_map = {
        'rtf': 'application/rtf',
        'txt': 'text/plain',
        'csv': 'text/csv',
        # Add other problematic types here
    }
    
    if extension in content_type_map:
        return content_type_map[extension]
    return content_type

def is_valid_file_type(filename: str, content_type: str) -> bool:
    extension = filename.lower().split('.')[-1] if '.' in filename else ''
    normalized_content_type = normalize_content_type(content_type, filename)
    
    return extension in SUPPORTED_EXTENSIONS and normalized_content_type in SUPPORTED_MIME_TYPES 