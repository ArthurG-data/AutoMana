
import json
from uuid import UUID
from datetime import datetime
from fastapi import Query
import ijson, asyncio
from backend.schemas.card_catalog import card as card_schemas
from backend.repositories.card_catalog.card_repository import CardReferenceRepository
from typing import  Optional, List, Dict, Any
from backend.schemas.card_catalog.card import BaseCard
from backend.exceptions.service_layer_exceptions.card_catalogue import card_exception
import logging
from dataclasses import dataclass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def add(card_repository : CardReferenceRepository
              , card : card_schemas.CreateCard
              ):
    values =  card.prepare_for_db()
    logger.info(f"Inserting card with values: {values}, number: {len(values)}")
    try:
        result = await card_repository.add(values)
        if result != "SELECT 1":
            raise card_exception.CardInsertError("Failed to insert card")
        return result
    except Exception as e:
        raise card_exception.CardInsertError(f"Failed to insert card: {str(e)}")


async def add_many(card_repository : CardReferenceRepository, cards: card_schemas.CreateCards):
    prepared_cards = cards.prepare_for_db()
    try:
        result = await card_repository.add_many(prepared_cards)

        return result 
    except Exception as e:
        raise card_exception.CardInsertError(f"Failed to insert cards: {str(e)}")

async def delete(card_repository : CardReferenceRepository, card_id: UUID)-> bool:
    try:
        result = await card_repository.delete(card_id)
        if not result:
            raise card_exception.CardDeletionError(f"Failed to delete card with ID {card_id}")
        return result
    except card_exception.CardDeletionError:
        raise
    except Exception as e:
        raise card_exception.CardDeletionError(f"Failed to delete card: {str(e)}")

async def search_cards(card_repository: CardReferenceRepository
                   , name: Optional[str] = None
                   , color: Optional[str] = None
                   , rarity: Optional[str] = None
                   , card_id: Optional[UUID] = None
                   , released_after: Optional[datetime] = None
                   , released_before: Optional[datetime] = None
                   , set_name: Optional[str] = None
                   , mana_cost: Optional[int] = None
                   , digital: Optional[bool] = None
                   , card_type: Optional[str] = None
                   # Pagination
                   , limit: int = 100
                   , offset: int = 0
                   , sort_by: str = "name"
                   , sort_order: str = "asc"
                   ) -> List[BaseCard]:
    logger.info(f"Searching for cards with: name={name}, color={color}, rarity={rarity}, card_id={card_id}, set_name={set_name}, mana_cost={mana_cost}, digital={digital}")
    try:
        if card_id:
            logger.info(f"Fetching card by ID: {card_id}")
            card = card_repository.get(card_id)
            if not card:
                return {"users": [], "total": 0}
            return {"users": [BaseCard.model_validate(card)]
                    , "total": 1
                    }

        result = await card_repository.search(name=name,
                                               color=color,
                                               rarity=rarity,
                                               set_name=set_name,
                                               mana_cost=mana_cost,
                                               digital=digital,
                                               released_after=released_after,
                                               released_before=released_before,
                                               limit=limit,
                                               offset=offset,
                                               sort_by=sort_by,
                                               card_type=card_type,
                                               sort_order=sort_order)
        if not result:
            raise card_exception.CardNotFoundError(f"No cards found for IDs {card_id}")
        cards = result.get("cards", [])
        total_count = result.get("total_count", 0)
        return  {
            "cards": cards,
            "total_count": total_count
        }

    except card_exception.CardNotFoundError:
        raise
    except Exception as e:
        raise card_exception.CardRetrievalError(f"Failed to retrieve cards: {str(e)}")


async def get(card_repository: CardReferenceRepository,
               card_id: UUID,
                     ) -> BaseCard:
    try:
        result = await card_repository.get(
            card_id=card_id,
        )
        if not result:
            raise card_exception.CardNotFoundError(f"Card with ID {card_id} not found")
        return BaseCard.model_validate(result)
    except card_exception.CardNotFoundError:
        raise
    except Exception as e:
        raise card_exception.CardRetrievalError(f"Failed to retrieve card: {str(e)}")
    


@dataclass
class ProcessingStats:
    """Track processing statistics"""
    total_cards: int = 0
    successful_inserts: int = 0
    failed_inserts: int = 0
    batches_processed: int = 0
    processing_errors: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        return (self.successful_inserts / self.total_cards * 100) if self.total_cards > 0 else 0
    
    @property
    def duration_seconds(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_cards": self.total_cards,
            "successful_inserts": self.successful_inserts,
            "failed_inserts": self.failed_inserts,
            "batches_processed": self.batches_processed,
            "processing_errors": self.processing_errors,
            "success_rate": round(self.success_rate, 2),
            "duration_seconds": round(self.duration_seconds, 2),
            "cards_per_second": round(self.total_cards / max(self.duration_seconds, 1), 1)
        }

from pathlib import Path
from typing import Optional, List, Dict, Any, AsyncGenerator, Callable
from dataclasses import dataclass
import time

@dataclass
class ProcessingConfig:
    """Configuration for file processing"""
    batch_size: int = 500
    max_retries: int = 3
    retry_delay: float = 1.0
    skip_validation_errors: bool = True
    progress_callback: Optional[Callable[[ProcessingStats], None]] = None
    save_failed_cards: bool = True
    failed_cards_file: Optional[str] = None

class EnhancedCardImportService:
    """Enhanced card import service with better error handling and monitoring"""
    
    def __init__(self, card_repository: CardReferenceRepository, config: ProcessingConfig = None):
        self.card_repository = card_repository
        self.config = config or ProcessingConfig()
        self.stats = ProcessingStats()
        self.failed_cards: List[Dict[str, Any]] = []

    def process_large_cards_json(
        self, 
        file_path: str,
        resume_from_batch: int = 0,
        validate_file_first: bool = True
    ) -> ProcessingStats:
        """Not async anymore"""
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
            if not self._validate_file(file_path):
                raise card_exception.CardInsertError(f"File validation failed: {file_path}")
            
            # Process the file
            self._process_file_stream(file_path, resume_from_batch)

            self.stats.end_time = datetime.utcnow()
            
            # Save failed cards if any
            if self.failed_cards and self.config.save_failed_cards:
                self._save_failed_cards()
            
            # Final summary
            self._log_processing_summary()

            return self.stats
            
        except Exception as e:
            self.stats.end_time = datetime.utcnow()
            logger.error(f"❌ File processing failed: {str(e)}")
            raise card_exception.CardInsertError(f"File processing failed: {str(e)}")

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


    def _process_file_stream(self, file_path: str, resume_from_batch: int = 0):
        """Process file using streaming with enhanced error handling"""
        batch = []
        batch_count = 0
        
        try:
            logger.info(f"📁 Opening file for streaming: {file_path}")
            with open(file_path, "rb") as f:
                cards_iter = ijson.items(f, "item")

                for card_json in cards_iter:
                    try:
                        # Skip batches if resuming
                        if batch_count < resume_from_batch:
                            if len(batch) >= self.config.batch_size:
                                batch = []
                                batch_count += 1
                                logger.info(f"⏭️ Skipped batch {batch_count} (resuming from {resume_from_batch})")
                            continue
                        
                        # Validate and create card
                        card = card_schemas.CreateCard.model_validate(card_json)
                        if card:
                            batch.append(card)
                            self.stats.total_cards += 1
                        
                        # Process batch when full
                        if len(batch) >= self.config.batch_size:
                            self._process_batch(batch, batch_count + 1)
                            batch = []
                            batch_count += 1
                            
                            # Progress callback
                            if self.config.progress_callback:
                                self.config.progress_callback(self.stats)
                        
                    except Exception as e:
                        self.stats.processing_errors += 1
                        logger.error(f"❌ Error processing card at position {self.stats.total_cards}: {str(e)}")
                        
                        # Save failed card for analysis
                        self.failed_cards.append({
                            "position": self.stats.total_cards,
                            "data": card_json,
                            "error": str(e)
                        })
                        
                        if not self.config.skip_validation_errors:
                            raise
                
                # Process remaining cards
                if batch:
                    self._process_batch(batch, batch_count + 1)
                    
        except Exception as e:
            logger.error(f"❌ Stream processing error: {str(e)}")
            raise

    async def _async_json_iter(self, json_iter) -> AsyncGenerator[Dict[str, Any], None]:
        """Convert synchronous JSON iterator to async"""
        """DEPRECATED"""
        for item in json_iter:
            yield item
            # Allow other coroutines to run
            await asyncio.sleep(0)

    def _process_batch(self, batch: List[card_schemas.CreateCard], batch_number: int):
        """Process a batch with retry logic"""
        retry_count = 0
        
        while retry_count <= self.config.max_retries:
            try:
                logger.info(f"🔄 Processing batch {batch_number} with {len(batch)} cards (attempt {retry_count + 1})")

                cards_obj = card_schemas.CreateCards(items=batch)
                result = self.card_repository.add_many(cards_obj.prepare_for_db())
                
                # Update statistics
                self.stats.successful_inserts += result.successful_inserts
                self.stats.failed_inserts += result.failed_inserts
                self.stats.batches_processed += 1

                logger.info(f"✅ Batch {batch_number} completed: {result.successful_inserts}/{len(batch)} cards inserted")

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
                    time.sleep(wait_time)  # Exponential backoff
                else:
                    # Save failed batch for manual inspection
                    self._save_failed_batch(batch, batch_number, str(e))
                    self.stats.failed_inserts += len(batch)
                    raise card_exception.CardInsertError(f"Batch {batch_number} failed after {self.config.max_retries} retries: {str(e)}")

    def _save_failed_cards(self):
        """Save failed cards to file for analysis"""
        if not self.failed_cards:
            return
        
        failed_file = self.config.failed_cards_file or f"failed_cards_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        
        try:
            with open(failed_file, 'w') as f:
                json.dump(self.failed_cards, f, indent=2, default=str)
            
            logger.info(f"💾 Saved {len(self.failed_cards)} failed cards to {failed_file}")
            
        except Exception as e:
            logger.error(f"❌ Failed to save failed cards: {str(e)}")

    def _save_failed_batch(self, batch: List[card_schemas.CreateCard], batch_number: int, error: str):
        """Save a failed batch for recovery"""
        batch_file = f"failed_batch_{batch_number}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        
        try:
            batch_data = {
                "batch_number": batch_number,
                "error": error,
                "cards": [card.model_dump() for card in batch]
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
        logger.info(f"📁 Total cards processed: {self.stats.total_cards}")
        logger.info(f"✅ Successful inserts: {self.stats.successful_inserts}")
        logger.info(f"❌ Failed inserts: {self.stats.failed_inserts}")
        logger.info(f"⚠️ Processing errors: {self.stats.processing_errors}")
        logger.info(f"📦 Batches processed: {self.stats.batches_processed}")
        logger.info(f"📈 Success rate: {self.stats.success_rate:.2f}%")
        logger.info(f"⏱️ Duration: {self.stats.duration_seconds:.2f} seconds")
        logger.info(f"🚀 Processing rate: {self.stats.total_cards / max(self.stats.duration_seconds, 1):.1f} cards/second")
        logger.info("=" * 60)

# ✅ BACKWARD COMPATIBLE: Keep your original function but enhanced
def process_large_cards_json(
    card_repository: CardReferenceRepository, 
    file_path: str,
    batch_size: int = 500,
    skip_validation_errors: bool = True,
    resume_from_batch: int = 0
) -> ProcessingStats:
    """
    Enhanced file processing with better error handling and monitoring
    
    Args:
        card_repository: Repository for database operations
        file_path: Path to JSON file (local or cloud URL)
        batch_size: Number of cards per batch
        skip_validation_errors: Whether to skip invalid cards or fail
        resume_from_batch: Batch number to resume from (for recovery)
    """
    
    config = ProcessingConfig(
        batch_size=batch_size,
        skip_validation_errors=skip_validation_errors,
        save_failed_cards=True,
        max_retries=3
    )
    
    service = EnhancedCardImportService(card_repository, config)
    return service.process_large_cards_json(
        file_path=file_path,
        resume_from_batch=resume_from_batch
    )
