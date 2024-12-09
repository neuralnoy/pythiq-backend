SUPPORTED_MIME_TYPES = {
    # Base types
    'application/pdf',
    
    # Documents and presentations
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    
    # Images
    'image/png'
}

SUPPORTED_EXTENSIONS = {
    'pdf', 'docx', 'pptx', 'xlsx', 'png'
}

def normalize_content_type(content_type: str, filename: str) -> str:
    """Normalize content type based on file extension if needed"""
    extension = filename.lower().split('.')[-1] if '.' in filename else ''
    
    # Map of extensions to content types that might need normalization
    content_type_map = {
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'png': 'image/png',
        'pdf': 'application/pdf'
    }
    
    if extension in content_type_map:
        return content_type_map[extension]
    return content_type

def is_valid_file_type(filename: str, content_type: str) -> bool:
    extension = filename.lower().split('.')[-1] if '.' in filename else ''
    normalized_content_type = normalize_content_type(content_type, filename)
    
    return extension in SUPPORTED_EXTENSIONS and normalized_content_type in SUPPORTED_MIME_TYPES 