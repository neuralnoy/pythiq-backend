from typing import Dict, Optional, List, Iterable, Any
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path
from enum import Enum
import json
import logging
import time
import tempfile

from ..client import s3_client, parsed_documents_table, documents_table
from ...core.config import settings
from ...schemas.parsed_document import ParseStatus
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat
from docling_core.types.doc import (
    DoclingDocument,
    NodeItem,
    PictureClassificationClass,
    PictureClassificationData,
    PictureItem,
)
from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
from docling.models.base_model import BaseEnrichmentModel

logger = logging.getLogger(__name__)

IMAGE_RESOLUTION_SCALE = 2.0

class ExportFormat(str, Enum):
    JSON = "json"
    TEXT = "txt"
    MARKDOWN = "md"
    DOCTAGS = "doctags"
    HTML = "html"

class CustomPdfPipelineOptions(PdfPipelineOptions):
    do_picture_classifier: bool = True
    
class CustomPictureClassifier(BaseEnrichmentModel):
    def __init__(self, enabled: bool):
        self.enabled = enabled

    def is_processable(self, doc: DoclingDocument, element: NodeItem) -> bool:
        return self.enabled and isinstance(element, PictureItem)

    def __call__(self, doc: DoclingDocument, element_batch: Iterable[NodeItem]) -> Iterable[Any]:
        if not self.enabled:
            return

        for element in element_batch:
            if isinstance(element, PictureItem):
                # Get the image
                image = element.get_image(doc)
                logger.info(f"Processing image: {element.self_ref}")

                # Add classification data
                element.annotations.append(
                    PictureClassificationData(
                        provenance="custom_classifier-0.0.1",
                        predicted_classes=[
                            PictureClassificationClass(
                                class_name="figure", 
                                confidence=0.95
                            )
                        ],
                    )
                )

                yield element

class CustomPdfPipeline(StandardPdfPipeline):
    def __init__(self, pipeline_options: CustomPdfPipelineOptions):
        super().__init__(pipeline_options)
        self.pipeline_options = pipeline_options
        
        # Add the picture classifier to the enrichment pipeline
        self.enrichment_pipe = [
            CustomPictureClassifier(enabled=pipeline_options.do_picture_classifier)
        ] + self.enrichment_pipe

class DocumentParser:
    def __init__(self):
        # Initialize pipeline options
        pipeline_options = CustomPdfPipelineOptions()
        pipeline_options.do_ocr = True
        pipeline_options.do_table_structure = True
        pipeline_options.table_structure_options.do_cell_matching = True
        pipeline_options.images_scale = IMAGE_RESOLUTION_SCALE
        pipeline_options.generate_picture_images = True
        pipeline_options.do_picture_classifier = True

        # Initialize document converter with custom pipeline
        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_cls=CustomPdfPipeline,
                    pipeline_options=pipeline_options
                )
            }
        )

    def parse_document(self, file_path: Path) -> Dict[str, str]:
        """
        Parse document and return all possible export formats
        """
        try:
            start_time = time.time()
            conv_result = self.converter.convert(file_path)
            end_time = time.time() - start_time
            
            logger.info(f"Document converted in {end_time:.2f} seconds")

            # Process images and store them
            images_data = []
            for element, level in conv_result.document.iterate_items():
                if isinstance(element, PictureItem):
                    try:
                        image = element.get_image(conv_result.document)
                        logger.info(f"Found image: {element.self_ref} at level {level}")
                        logger.info(f"Image annotations: {element.annotations}")
                        
                        # Store image data
                        images_data.append({
                            'ref': element.self_ref,
                            'level': level,
                            'annotations': [
                                {
                                    'provenance': ann.provenance,
                                    'classes': [
                                        {'name': cls.class_name, 'confidence': cls.confidence}
                                        for cls in ann.predicted_classes
                                    ]
                                }
                                for ann in element.annotations
                                if isinstance(ann, PictureClassificationData)
                            ]
                        })
                    except Exception as e:
                        logger.error(f"Error processing image {element.self_ref}: {str(e)}")

            # Generate all export formats
            exports = {
                ExportFormat.JSON: json.dumps({
                    'document': conv_result.document.export_to_dict(),
                    'images': images_data
                }),
                ExportFormat.TEXT: conv_result.document.export_to_text(),
                ExportFormat.MARKDOWN: conv_result.document.export_to_markdown(),
                ExportFormat.DOCTAGS: conv_result.document.export_to_document_tokens()
            }

            # Try HTML export if available
            try:
                exports[ExportFormat.HTML] = conv_result.document.export_to_html()
            except AttributeError:
                logger.info("HTML export not available for this document type")

            return exports

        except Exception as e:
            logger.error(f"Error parsing document: {str(e)}")
            raise

class ParsedDocumentRepository:
    def __init__(self):
        self.parser = DocumentParser()
    
    async def parse_document(self, document: Dict) -> Dict:
        try:
            parsed_id = str(uuid4())
            original_path = document['path']
            base_parsed_path = f"{document['user_id']}/{document['knowledge_base_id']}/{document['id']}/parsed/{parsed_id}"
            
            # Create initial metadata record
            parsed_metadata = {
                'id': parsed_id,
                'document_id': document['id'],
                'knowledge_base_id': document['knowledge_base_id'],
                'user_id': document['user_id'],
                'original_path': original_path,
                'parsed_paths': {},
                'parse_status': ParseStatus.PROCESSING,
                'parsed_at': datetime.now(timezone.utc).isoformat(),
            }

            # Download and process file
            with tempfile.NamedTemporaryFile(suffix=Path(document['name']).suffix, delete=False) as temp_file:
                s3_response = s3_client.get_object(
                    Bucket=settings.AWS_BUCKET_NAME,
                    Key=original_path
                )
                temp_file.write(s3_response['Body'].read())
                temp_file.flush()

                # Parse document in all formats
                exports = self.parser.parse_document(Path(temp_file.name))

                # Upload all formats to S3
                for format_type, content in exports.items():
                    parsed_path = f"{base_parsed_path}.{format_type}"
                    s3_client.put_object(
                        Bucket=settings.AWS_BUCKET_NAME,
                        Key=parsed_path,
                        Body=content.encode('utf-8'),
                        ContentType=f'text/{format_type}'
                    )
                    parsed_metadata['parsed_paths'][format_type] = parsed_path

            # Update status and save metadata
            parsed_metadata['parse_status'] = ParseStatus.COMPLETED
            parsed_documents_table.put_item(Item=parsed_metadata)

            return parsed_metadata

        except Exception as e:
            logger.error(f"Error in parse_document: {str(e)}")
            parsed_metadata['parse_status'] = ParseStatus.FAILED
            parsed_metadata['error_message'] = str(e)
            parsed_documents_table.put_item(Item=parsed_metadata)
            raise

    async def get_parsed_documents(
        self,
        document_id: str,
        knowledge_base_id: str,
        user_id: str
    ) -> List[Dict]:
        """Get all parsed versions of a document"""
        try:
            response = parsed_documents_table.query(
                KeyConditionExpression='document_id = :did',
                FilterExpression='user_id = :uid AND knowledge_base_id = :kid',
                ExpressionAttributeValues={
                    ':did': document_id,
                    ':uid': user_id,
                    ':kid': knowledge_base_id
                }
            )
            return response.get('Items', [])
        except Exception as e:
            logger.error(f"Error fetching parsed documents: {str(e)}")
            raise

    async def get_parsed_content(
        self,
        parsed_id: str,
        document_id: str,
        knowledge_base_id: str,
        user_id: str
    ) -> str:
        """Get the content of a specific parsed version"""
        try:
            # Get metadata to verify access and get path
            response = parsed_documents_table.get_item(
                Key={'id': parsed_id}
            )
            metadata = response.get('Item')
            
            if not metadata or metadata['user_id'] != user_id:
                raise Exception("Parsed document not found or access denied")
            
            # Get content from S3
            s3_response = s3_client.get_object(
                Bucket=settings.AWS_BUCKET_NAME,
                Key=metadata['parsed_path']
            )
            
            return s3_response['Body'].read().decode('utf-8')
        except Exception as e:
            logger.error(f"Error fetching parsed content: {str(e)}")
            raise

# Initialize the repository
parsed_document_repository = ParsedDocumentRepository()
