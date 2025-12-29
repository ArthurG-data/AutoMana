import asyncio, json, ijson, logging
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from typing import Any, AsyncGenerator, Callable, Dict, List,  Optional
from backend.repositories.card_catalog.set_repository import SetReferenceRepository
from backend.schemas.card_catalog.set import  SetInDB, NewSet, UpdatedSet, NewSets
from backend.exceptions.service_layer_exceptions.card_catalogue import set_exception
from backend.shared.utils import decode_json_input
from backend.core.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)

@ServiceRegistry.register(
    "card_catalog.set.get",
    db_repositories=["set_reference"]
)
async def get(set_repository: SetReferenceRepository
              , set_id: UUID) -> SetInDB:
    try:
        result = await set_repository.get(set_id)
        if not result:
            raise set_exception.SetNotFoundError(f"Set with ID {set_id} not found")
        return SetInDB.model_validate(result)
    except set_exception.SetNotFoundError:
        raise
    except Exception as e:
        raise set_exception.SetRetrievalError(f"Failed to retrieve set: {str(e)}")

@ServiceRegistry.register(
    "card_catalog.set.get_all",
    db_repositories=["set_reference"]
)
async def get_all(set_repository: SetReferenceRepository
                  ,limit: Optional[int] = None
                  ,offset: Optional[int] = None
                  ,ids: Optional[List[UUID]] = None
                  ) -> List[SetInDB]:
    try:
        results = await set_repository.list(limit=limit, offset=offset, ids=ids)
        if not results:
            raise set_exception.SetNotFoundError("No sets found")
        return [SetInDB.model_validate(result) for result in results]
    except set_exception.SetNotFoundError:
        raise
    except Exception as e:
        raise set_exception.SetRetrievalError(f"Failed to retrieve sets: {str(e)}")

@ServiceRegistry.register(
    "card_catalog.set.add",
    db_repositories=["set_reference"]
)
async def add_set(set_repository: SetReferenceRepository
                  , new_set: NewSet
                  ) -> bool:
    data = new_set.create_values()
    #values = tuple(v for _, v in data.items())
    try:
        result = await set_repository.add(*data)
        if not result:
            raise set_exception.SetCreationError("Failed to create set")
        return True if result == 1 else False
    except set_exception.SetCreationError:
        raise
    
@ServiceRegistry.register(
    "card_catalog.set.create_bulk",
    db_repositories=["set_reference"]
)
async def add_sets_bulk(set_repository: SetReferenceRepository, new_sets: NewSets) -> List[SetInDB]:
    """ Adds multiple sets to the database in a single transaction."""
    data = [set.create_values() for set in new_sets]
    print(data)
    try:
        results = await set_repository.add_many(data)
        if not results or len(results) == 0:
            raise set_exception.SetCreationError("Failed to create sets")
        return [SetInDB.model_validate(result) for result in results]
    except set_exception.SetCreationError:
        raise
    except Exception as e:
        raise set_exception.SetCreationError(f"Failed to create sets: {str(e)}")

@ServiceRegistry.register(
    "card_catalog.set.update",
    db_repositories=["set_reference"]
)
async def put_set(set_repository: SetReferenceRepository, set_id: UUID, update_set: UpdatedSet):
    try:
        not_nul = {k: v for k, v in update_set.model_dump().items() if v is not None}
        if not_nul == {}:
            raise set_exception.SetUpdateError("No fields to update")

        result = await set_repository.update(set_id, not_nul)
        if not result:
            raise set_exception.SetNotFoundError(f"Failed to update set with ID {set_id}")
        return SetInDB.model_validate(result)
    except set_exception.SetNotFoundError:
        raise
    except Exception as e:
        raise set_exception.SetUpdateError(f"Failed to update set: {str(e)}")

@ServiceRegistry.register(
    "card_catalog.set.delete",
    db_repositories=["set_reference"]
)
async def delete_set(set_repository: SetReferenceRepository
                     , set_id: UUID) -> bool:
    try:
        result = await set_repository.delete(set_id)
        if not result:
            raise set_exception.SetNotFoundError(f"Failed to delete set with ID {set_id}")
        return True
    except set_exception.SetNotFoundError:
        raise
    except Exception as e:
        raise set_exception.SetDeletionError(f"Failed to delete set: {str(e)}")

async def get_parsed_set(file_content : bytes)-> NewSets:
    """Dependency that parses sets from an uploaded JSON file."""
    try:
        data =  await decode_json_input(file_content)
        return NewSets(items = data)
    except Exception as e:
        raise set_exception.SetParsingError(f"Failed to parse sets from JSON: {str(e)}") 
    
@dataclass
class ProcessingStats:
    """Track processing statistics"""
    total_sets: int = 0
    successful_inserts: int = 0
    failed_inserts: int = 0
    batches_processed: int = 0
    processing_errors: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        return (self.successful_inserts / self.total_sets * 100) if self.total_sets > 0 else 0

    @property
    def duration_seconds(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_sets": self.total_sets,
            "successful_inserts": self.successful_inserts,
            "failed_inserts": self.failed_inserts,
            "batches_processed": self.batches_processed,
            "processing_errors": self.processing_errors,
            "success_rate": round(self.success_rate, 2),
            "duration_seconds": round(self.duration_seconds, 2),
            "sets_per_second": round(self.total_sets / max(self.duration_seconds, 1), 1)
        }
    
@dataclass
class ProcessingConfig:
    """Configuration for file processing"""
    batch_size: int = 500
    max_retries: int = 3
    retry_delay: float = 1.0
    skip_validation_errors: bool = True
    progress_callback: Optional[Callable[[ProcessingStats], None]] = None
    save_failed_sets: bool = True
    failed_sets_file: Optional[str] = None

@ServiceRegistry.register(
    "card_catalog.set.process_large_sets_json",
    db_repositories=["set"]
)
async def process_large_sets_json(
    set_repository: SetReferenceRepository,
    file_path: str,
    config: ProcessingConfig = None,
    resume_from_batch: int = 0
) -> dict:
    """Process large JSON file containing sets using streaming to minimize memory usage"""
    processor = EnhancedSetImportService(set_repository, config)
    result : ProcessingStats =  await processor.process_large_sets_json(
        file_path=file_path,
        resume_from_batch=resume_from_batch
    )
    return result.to_dict()

class EnhancedSetImportService:
    """Enhanced set import service with better error handling and monitoring"""
    
    def __init__(self, set_repository: SetReferenceRepository, config: ProcessingConfig = None):
        self.set_repository = set_repository
        self.config = config or ProcessingConfig()
        self.stats = ProcessingStats()
        self.failed_sets: List[Dict[str, Any]] = []

    async def process_large_sets_json(
        self, 
        file_path: str,
        resume_from_batch: int = 0,
        validate_file_first: bool = True
    ) -> ProcessingStats:
        """
        Process large JSON file with enhanced error handling and monitoring
        
        Args:
            file_path: Path to JSON file (local or cloud)
            resume_from_batch: Batch number to resume from (for recovery)
            validate_file_first: Whether to validate JSON structure first
        """
        try:
            logger.info(f"🚀 Starting enhanced file processing: {file_path}")
            self.stats.start_time = datetime.utcnow()
            
            # Validate file exists and is readable
            if validate_file_first and not self._validate_file(file_path):
                raise set_exception.SetInsertError(f"File validation failed: {file_path}")

            # Process the file
            await self._process_file_stream(file_path, resume_from_batch)

            self.stats.end_time = datetime.utcnow()
            # Save failed sets if any
            if self.failed_sets and self.config.save_failed_sets:
                self._save_failed_sets()
            
            # Final summary
            self._log_processing_summary()
            
            return self.stats
            
        except Exception as e:
            self.stats.end_time = datetime.utcnow()
            logger.error(f"❌ File processing failed: {str(e)}")
            raise set_exception.SetInsertError(f"File processing failed: {str(e)}")

    def _validate_file(self, file_path: str) -> bool:
        """Validate file exists and is accessible"""
        try:
            path = Path(file_path)
            if not path.exists():
                logger.error(f"❌ File does not exist: {file_path}")
                return False
            
            if not path.is_file():
                logger.error(f"❌ Path is not a file: {file_path}")
                return False
            
            # Check file size (warn if very large)
            file_size = path.stat().st_size
            if file_size > 500 * 1024 * 1024:  # 500MB
                logger.warning(f"⚠️ Large file detected: {file_size / 1024 / 1024:.1f}MB")
            
            logger.info(f"✅ File validation passed: {file_size / 1024 / 1024:.1f}MB")
            return True
            
        except Exception as e:
            logger.error(f"❌ File validation error: {str(e)}")
            return False


    async def _process_file_stream(self, file_path: str, resume_from_batch: int = 0):
        """Process file using streaming with enhanced error handling"""
        batch = []
        batch_count = 0
        logger.info(f"📁 Opening file for streaming: {file_path}")

        try:
            with open(file_path, "rb") as f:
                sets_iter = ijson.items(f, "data.item")
                for set_json in sets_iter:
                    try:
                        # Skip batches if resuming
                        
                        if batch_count < resume_from_batch:
                            if len(batch) >= self.config.batch_size:
                                batch = []
                                batch_count += 1
                                logger.info(f"⏭️ Skipped batch {batch_count} (resuming from {resume_from_batch})")
                            continue

                        # Validate and create set
                        set_object = NewSet.model_validate(set_json)
                        if set_object:
                            batch.append(set_object)
                            self.stats.total_sets += 1

                        # Process batch when full
                        if len(batch) >= self.config.batch_size:
                            logger.info("📦 processing batch %s (%s sets)", batch_count + 1, len(batch))
                            await self._process_batch(batch, batch_count + 1)
                            batch = []
                            batch_count += 1
                            logger.info("✅ finished batch %s", batch_count + 1)
                            # Progress callback
                            if self.config.progress_callback:
                                self.config.progress_callback(self.stats)
                            
                            await asyncio.sleep(0)
                        
                    except Exception as e:
                        self.stats.processing_errors += 1   
                        logger.error(f"❌ Error processing set at position {self.stats.total_sets}: {str(e)}, {set}")

                        # Save failed set for analysis
                        self.failed_sets.append({
                            "position": self.stats.total_sets,
                            "data": set_json,
                            "error": str(e)
                        })
                        
                        if not self.config.skip_validation_errors:
                            raise
                
                # Process remaining cards
                if batch:
                    batch = [x for x in batch if x is not None]
                    if batch:
                        await self._process_batch(batch, batch_count + 1)
                    
        except Exception as e:
            logger.error(f"❌ Stream processing error: {str(e)}")
            raise

    async def _async_json_iter(self, json_iter) -> AsyncGenerator[Dict[str, Any], None]:
        """Convert synchronous JSON iterator to async"""
        for item in json_iter:
            yield item
            # Allow other coroutines to run
            await asyncio.sleep(0)

    async def _process_batch(self, batch: List[NewSet], batch_number: int):
        """Process a batch with retry logic"""
        retry_count = 0
        while retry_count <= self.config.max_retries:
            try:
                logger.info(f"🔄 Processing batch {batch_number} with {len(batch)} sets (attempt {retry_count + 1})")

                sets_obj = NewSets(items=batch)
                result = await self.set_repository.add_many(sets_obj.prepare_for_db())

                # Update statistics
                self.stats.successful_inserts += result.successful_inserts
                self.stats.failed_inserts += result.failed_inserts
                self.stats.batches_processed += 1

                logger.info(f"✅ Batch {batch_number} completed: {result.successful_inserts}/{len(batch)} sets inserted")

                # Log any errors from this batch
                if result.errors:
                    for error in result.errors[:3]:  # Log first 3 errors
                        logger.warning(f"⚠️ Batch {batch_number} error: {error}")
                
                return result
                
            except Exception as e:
                retry_count += 1
                logger.error(f"❌ Batch {batch_number} failed (attempt {retry_count}): {str(e)}")
                
                if retry_count <= self.config.max_retries:
                    wait_time = self.config.retry_delay * retry_count
                    logger.info(f"⏳ Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)  # Exponential backoff
                else:
                    # Save failed batch for manual inspection
                    self._save_failed_batch(batch, batch_number, str(e))
                    self.stats.failed_inserts += len(batch)
                    raise set_exception.SetInsertError(f"Batch {batch_number} failed after {self.config.max_retries} retries: {str(e)}")

    def _save_failed_sets(self):
        """Save failed sets to file for analysis"""
        if not self.failed_sets:
            return

        failed_file = self.config.failed_sets_file or f"failed_sets_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"

        try:
            with open(failed_file, 'w') as f:
                json.dump(self.failed_sets, f, indent=2, default=str)

            logger.info(f"💾 Saved {len(self.failed_sets)} failed sets to {failed_file}")
            
        except Exception as e:
            logger.error(f"❌ Failed to save failed sets: {str(e)}")

    def _save_failed_batch(self, batch: List[NewSet], batch_number: int, error: str):
        """Save a failed batch for recovery"""
        batch_file = f"failed_batch_{batch_number}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        
        try:
            batch_data = {
                "batch_number": batch_number,
                "error": error,
                "sets": [set.model_dump() for set in batch]
            }
            
            with open(batch_file, 'w') as f:
                json.dump(batch_data, f, indent=2, default=str)
            
            logger.info(f"💾 Saved failed batch {batch_number} to {batch_file}")
            
        except Exception as e:
            logger.error(f"❌ Failed to save failed batch: {str(e)}")

    def _log_processing_summary(self):
        """Log comprehensive processing summary"""
        logger.info("=" * 60)
        logger.info("📊 FILE PROCESSING SUMMARY")
        logger.info("=" * 60)
        logger.info(f"📁 Total sets processed: {self.stats.total_sets}")
        logger.info(f"✅ Successful inserts: {self.stats.successful_inserts}")
        logger.info(f"❌ Failed inserts: {self.stats.failed_inserts}")
        logger.info(f"⚠️ Processing errors: {self.stats.processing_errors}")
        logger.info(f"📦 Batches processed: {self.stats.batches_processed}")
        logger.info(f"📈 Success rate: {self.stats.success_rate:.2f}%")
        logger.info(f"⏱️ Duration: {self.stats.duration_seconds:.2f} seconds")
        logger.info(f"🚀 Processing rate: {self.stats.total_sets / max(self.stats.duration_seconds, 1):.1f} sets/second")
        logger.info("=" * 60)
