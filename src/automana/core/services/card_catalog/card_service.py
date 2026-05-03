from uuid import UUID
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import  Optional, List, Dict, Any, Callable
from pathlib import Path
import hashlib
import ijson, asyncio, logging, json
from automana.core.repositories.ops.ops_repository import OpsRepository
from automana.core.services.ops.pipeline_services import track_step
from automana.core.models.card_catalog import card as card_schemas
from automana.core.repositories.card_catalog.card_repository import CardReferenceRepository
from automana.core.models.card_catalog.card import BaseCard, CardDetail, CardSuggestion, CardSuggestionResponse, CatalogStats
from automana.core.exceptions.service_layer_exceptions.card_catalogue import card_exception
from automana.core.service_registry import ServiceRegistry
from automana.core.models.pipelines.mtg_stock import  MTGStockBatchStep
from automana.core.storage import StorageService
from automana.core.utils.redis_cache import get_from_cache, set_to_cache, redis_client

logger = logging.getLogger(__name__)

@dataclass
class CardSearchResult:
    cards: List[BaseCard]
    total_count: int

@dataclass
class ProcessingStats:
    """Track processing statistics"""
    total_cards: int = 0
    successful_inserts: int = 0
    failed_inserts: int = 0
    batches_processed: int = 0
    processing_errors: int = 0
    skipped_inserts: int = 0
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
            "skipped_inserts": self.skipped_inserts,
            "batches_processed": self.batches_processed,
            "processing_errors": self.processing_errors,
            "success_rate": round(self.success_rate, 2),
            "duration_seconds": round(self.duration_seconds, 2),
            "cards_per_second": round(self.total_cards / max(self.duration_seconds, 1), 1)
        }
@dataclass
class ProcessingConfig:
    """Configuration for file processing"""
    batch_size: int = 500
    max_retries: int = 3
    retry_delay: float = 1.0
    skip_validation_errors: bool = True
    progress_callback: Optional[Callable[[ProcessingStats], None]] = None
    save_failed_cards: bool = True
    
@ServiceRegistry.register(
    "card_catalog.card.create",
    db_repositories=["card"],
    storage_services=["scryfall"]
)
async def add(card_repository : CardReferenceRepository
              , card : card_schemas.CreateCard
              ):
    values =  card.prepare_for_db()
    logger.info("Inserting card", extra={"values_count": len(values)})
    try:
        result = await card_repository.add(values)
        if result != "SELECT 1":
            raise card_exception.CardInsertError("Failed to insert card")
        return result
    except Exception as e:
        raise card_exception.CardInsertError(f"Failed to insert card: {str(e)}")

@ServiceRegistry.register(
    "card_catalog.card.create_many",
    db_repositories=["card"]
)
async def add_many(card_repository : CardReferenceRepository, cards: card_schemas.CreateCards):
    prepared_cards = cards.prepare_for_db()
    try:
        result = await card_repository.add_many(prepared_cards)

        return result 
    except Exception as e:
        raise card_exception.CardInsertError(f"Failed to insert cards: {str(e)}")

@ServiceRegistry.register(
    "card_catalog.card.delete",
    db_repositories=["card"]
)
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

@ServiceRegistry.register(
    "card_catalog.card.stats",
    db_repositories=["card", "ops"]
)
async def get_catalog_stats(
    card_repository: CardReferenceRepository,
    ops_repository: OpsRepository,
) -> dict:
    counts = await card_repository.fetch_card_universe_counts()
    last_updated = await ops_repository.fetch_latest_successful_run_ended_at("scryfall_daily")
    return {
        "total_card_versions": counts["total_card_versions"],
        "data_source": "Scryfall",
        "last_updated": last_updated,
    }

@ServiceRegistry.register(
    "card_catalog.card.search",
    db_repositories=["card"]
)
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
                   , oracle_text: Optional[str] = None
                   , format: Optional[str] = None
                   # Pagination
                   , limit: int = 100
                   , offset: int = 0
                   , sort_by: str = "name"
                   , sort_order: str = "asc"
                   ) -> CardSearchResult:
    logger.info("Searching cards", extra={"card_name": name, "color": color, "rarity": rarity, "card_id": str(card_id) if card_id else None, "set_name": set_name, "mana_cost": mana_cost, "digital": digital})
    try:
        params = {
            "name": name,
            "color": color,
            "rarity": rarity,
            "card_id": str(card_id) if card_id else None,
            "released_after": str(released_after) if released_after else None,
            "released_before": str(released_before) if released_before else None,
            "set_name": set_name,
            "mana_cost": mana_cost,
            "digital": digital,
            "card_type": card_type,
            "oracle_text": oracle_text,
            "format": format,
            "limit": limit,
            "offset": offset,
            "sort_by": sort_by,
            "sort_order": sort_order,
        }
        params_hash = hashlib.sha256(
            json.dumps(params, sort_keys=True, default=str).encode()
        ).hexdigest()
        cache_key = f"card_search:full:{params_hash}"

        cached = get_from_cache(cache_key)
        if cached is not None:
            return CardSearchResult(
                cards=[BaseCard.model_validate(c) for c in cached["cards"]],
                total_count=cached["total_count"],
            )

        if card_id:
            logger.info("Fetching card by ID", extra={"card_id": str(card_id)})
            card = await card_repository.get(card_id)
            if not card:
                return CardSearchResult(cards=[], total_count=0)
            result = CardSearchResult(cards=[BaseCard.model_validate(card)], total_count=1)
        else:
            raw = await card_repository.search(name=name,
                                               color=color,
                                               rarity=rarity,
                                               set_name=set_name,
                                               mana_cost=mana_cost,
                                               digital=digital,
                                               released_after=released_after,
                                               released_before=released_before,
                                               oracle_text=oracle_text,
                                               format=format,
                                               limit=limit,
                                               offset=offset,
                                               sort_by=sort_by,
                                               card_type=card_type,
                                               sort_order=sort_order)
            if not raw:
                raise card_exception.CardNotFoundError(f"No cards found for IDs {card_id}")
            cards = raw.get("cards", [])
            total_count = raw.get("total_count", 0)
            result = CardSearchResult(
                cards=[BaseCard.model_validate(card) for card in cards],
                total_count=total_count,
            )

        cache_data = {"cards": [c.model_dump() for c in result.cards], "total_count": result.total_count}
        set_to_cache(
            cache_key,
            json.loads(BaseCard.to_json_safe(cache_data)),
            expiry_seconds=3600,
        )
        return result

    except card_exception.CardNotFoundError:
        raise
    except Exception as e:
        raise card_exception.CardRetrievalError(f"Failed to retrieve cards: {str(e)}")


@ServiceRegistry.register(
    "card_catalog.card.suggest",
    db_repositories=["card"]
)
async def suggest_cards(
    card_repository: CardReferenceRepository,
    query: str,
    limit: int = 10,
    **kwargs,
) -> CardSuggestionResponse:
    cache_key = f"card_search:suggest:{query.lower()}:{limit}"
    cached = get_from_cache(cache_key)
    if cached is not None:
        return CardSuggestionResponse(suggestions=[CardSuggestion(**s) for s in cached])

    rows = await card_repository.suggest(query=query, limit=limit)
    suggestions = [CardSuggestion(**r) for r in rows]
    set_to_cache(cache_key, [s.model_dump(mode="json") for s in suggestions], expiry_seconds=600)
    return CardSuggestionResponse(suggestions=suggestions)


@ServiceRegistry.register(
    "card_catalog.card_search.invalidate",
    db_repositories=[]
)
async def invalidate_search_cache(**kwargs) -> dict:
    keys = list(redis_client.scan_iter("card_search:*"))
    if keys:
        redis_client.delete(*keys)
    logger.info("Invalidated card search cache", extra={"keys_deleted": len(keys)})
    return {"keys_deleted": len(keys)}


@ServiceRegistry.register(
    "card_catalog.card_search.refresh",
    db_repositories=["card"]
)
async def refresh_card_search_views(
    card_repository: CardReferenceRepository,
    **kwargs,
) -> dict:
    await card_repository.connection.execute("CALL card_catalog.refresh_card_search_views()")
    logger.info("Refreshed card search materialized views")
    return {"refreshed": True}


@ServiceRegistry.register(
    "card_catalog.card.get",
    db_repositories=["card"]
)
async def get(card_repository: CardReferenceRepository,
               card_id: UUID,
                     ) -> CardSearchResult:
    try:
        result = await card_repository.get(
            card_id=card_id,
        )
        if not result:
            return CardSearchResult(cards=[], total_count=0)
        return CardSearchResult(cards=[CardDetail.model_validate(result)], total_count=1)
    except card_exception.CardNotFoundError:
        raise
    except Exception as e:
        raise card_exception.CardRetrievalError(f"Failed to retrieve card: {str(e)}")

@ServiceRegistry.register(
    "card_catalog.card.register_external_identifier",
    db_repositories=["card"],
)
async def register_external_identifier(
    card_repository: CardReferenceRepository,
    card_version_id: UUID,
    identifier_name: str,
    value: str,
) -> bool:
    """Idempotently attach an external identifier to a card_version. Returns True on insert, False on no-op."""
    try:
        outcome = await card_repository.register_external_identifier(
            card_version_id=card_version_id,
            identifier_name=identifier_name,
            value=value,
        )

        if not outcome.ref_found:
            logger.warning(
                "Unknown external identifier name",
                extra={
                    "card_version": str(card_version_id),
                    "identifier": identifier_name,
                },
            )
            raise card_exception.UnknownIdentifierNameError(
                f"Unknown identifier_name '{identifier_name}' — not registered "
                f"in card_catalog.card_identifier_ref"
            )
        if not outcome.card_version_exists:
            logger.warning(
                "card_version not found for external identifier registration",
                extra={
                    "card_version": str(card_version_id),
                    "identifier": identifier_name,
                },
            )
            raise card_exception.CardNotFoundError(
                f"card_version {card_version_id} not found"
            )

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "External identifier registered",
                extra={
                    "card_version": str(card_version_id),
                    "identifier": identifier_name,
                    "inserted": outcome.inserted,
                },
            )
        return outcome.inserted

    except (
        card_exception.UnknownIdentifierNameError,
        card_exception.CardNotFoundError,
    ):
        raise
    except Exception as e:
        raise card_exception.CardInsertError(
            f"Failed to register external identifier "
            f"(card_version={card_version_id}, identifier={identifier_name}): {e}"
        )


@ServiceRegistry.register(
    "card_catalog.card.process_large_json",
    db_repositories=["card", "ops"],
    storage_services=["scryfall", "errors"]
)
async def process_large_cards_json(
    card_repository: CardReferenceRepository,
    file_name: str,
    ops_repository: OpsRepository = None,
    ingestion_run_id: int = None,
    resume_from_batch: int = 0,
    validate_file_first: bool = True,
    storage_service: StorageService = None,
    errors_storage_service: StorageService = None,
) -> dict:
    """Process large JSON file with enhanced error handling and monitoring
    
    Args:
        card_repository: Repository for card operations
        file_path: Path to JSON file (local or cloud)
        resume_from_batch: Batch number to resume from (for recovery)
        validate_file_first: Whether to validate JSON structure first
    """
    service = EnhancedCardImportService(card_repository, storage_service=storage_service, errors_storage_service=errors_storage_service)
    if not file_name:
        logger.info("No bulk card changes — skipping processing", extra={"ingestion_run_id": ingestion_run_id})
        return {"status": "success"}
    async with track_step(ops_repository, ingestion_run_id, "process_large_cards_json", error_code="processing_failed"):
        result = await service.process_large_cards_json(
            file_name=file_name,
            resume_from_batch=resume_from_batch,
            validate_file_first=validate_file_first,
            ops_repository=ops_repository,
            ingestion_run_id=ingestion_run_id
        )
    return result.to_dict()


class EnhancedCardImportService:
    """Enhanced card import service with better error handling and monitoring"""
    
    def __init__(self, card_repository: CardReferenceRepository, config: ProcessingConfig = None, storage_service: StorageService = None, errors_storage_service: StorageService = None):
        self.card_repository = card_repository
        self.config = config or ProcessingConfig()
        self.stats = ProcessingStats()
        self.failed_cards: List[Dict[str, Any]] = []
        self.storage_service = storage_service
        self.errors_storage_service = errors_storage_service

    async def process_large_cards_json(
        self, 
        file_name: str,
        resume_from_batch: int = 0,
        validate_file_first: bool = True,
        ops_repository: OpsRepository = None,
        ingestion_run_id: int = None
    ) -> ProcessingStats:
        """Not async anymore"""
        """
        Process large JSON file with enhanced error handling and monitoring
        
        Args:
            file_name: Name of the JSON file (local or cloud)
            resume_from_batch: Batch number to resume from (for recovery)
            validate_file_first: Whether to validate JSON structure first
            ops_repository: Repository for operations logging
            ingestion_run_id: ID for the current ingestion run
        """
        try:
            logger.info("Starting card file processing", extra={"file_path": file_name})
            self.stats.start_time = datetime.now(timezone.utc)
            
            # Validate file exists and is readable
            if not await self._validate_file(file_name):
                raise card_exception.CardInsertError(f"File validation failed: {file_name}")
            
            self.failed_cards_filename = f"failed_cards_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.jsonl"
            # Process the file
            await self._process_file_stream(file_name, resume_from_batch)

            self.stats.end_time = datetime.now(timezone.utc)
            # Final summary
            self._log_processing_summary()
            return self.stats
            
        except Exception as e:
            self.stats.end_time = datetime.now(timezone.utc)
            logger.error("Card file processing failed", extra={"file_path": file_name, "error": str(e)})
            raise card_exception.CardInsertError(f"File processing failed: {str(e)}")

    async def _validate_file(self, file_name: str) -> bool:
        """Validate file exists and is accessible"""
        try:
            file_exist = await self.storage_service.file_exists(file_name)
            print(file_exist)  # This will raise if file doesn't exist or is not accessible
            if not file_exist:
                logger.error("Card file not found", extra={"file_path": file_name})
                return False
            
            
            # Check file size (warn if very large)
            file_size = await self.storage_service.get_file_size(file_name)
            if file_size > 500 * 1024 * 1024:  # 500MB
                logger.warning("Large file detected", extra={"file_path": file_name, "size_mb": round(file_size / 1024 / 1024, 1)})
            
            logger.info("File validation passed", extra={"file_path": file_name, "size_mb": round(file_size / 1024 / 1024, 1)})
            return True
            
        except Exception as e:
            logger.error("File validation error", extra={"file_path": file_name, "error": str(e)})
            return False


    async def _process_file_stream(self
                                   , file_name: str
                                   , resume_from_batch: int = 0
                                   , ops_repository: OpsRepository = None
                                   , ingestion_run_id: int = None ):
        """Process file using streaming with enhanced error handling"""
        batch = []
        batch_count = 0
        
        try:
            logger.info("Opening file for streaming", extra={"file_path": file_name})
            async with self.storage_service.open_stream(file_name, "rb") as f:
                cards_iter = ijson.items(f, "item")

                for card_json in cards_iter:
                    try:
                        # Skip batches if resuming
                        if batch_count < resume_from_batch:
                            if len(batch) >= self.config.batch_size:
                                batch = []
                                batch_count += 1
                                logger.info("Skipped batch — resuming", extra={"batch": batch_count, "resume_from": resume_from_batch})
                
                            continue
                        
                        # Validate and create card
                        card = card_schemas.CreateCard.model_validate(card_json)
                        if card:
                            batch.append(card)
                            self.stats.total_cards += 1
                        
                        # Process batch when full
                        if len(batch) >= self.config.batch_size:

                            await self._process_batch(batch, batch_count + 1, ops_repository=ops_repository, ingestion_run_id=ingestion_run_id)
                            batch = []
                            batch_count += 1
                            await self._save_failed_cards()
                            # Progress callback,  test with one bacth
                            if self.config.progress_callback:
                                self.config.progress_callback(self.stats)
                           
                    except Exception as e:
                        self.stats.processing_errors += 1
                        logger.error("Card validation error", extra={"position": self.stats.total_cards, "error": str(e)})
                        
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
                    await self._process_batch(batch, batch_count + 1, ops_repository=ops_repository, ingestion_run_id=ingestion_run_id)
                await self._save_failed_cards()    
        except Exception as e:
            logger.error("Stream processing error", extra={"error": str(e)})
            raise

    async def _process_batch(self, batch: List[card_schemas.CreateCard]
                             , batch_number: int
                             , ops_repository: OpsRepository = None
                             , ingestion_run_id: int = None):
        """Process a batch with retry logic"""
        retry_count = 0
        while retry_count <= self.config.max_retries:

            try:
                logger.info("Processing batch", extra={"batch_number": batch_number, "size": len(batch), "attempt": retry_count + 1})

                cards_obj = card_schemas.CreateCards(items=batch)

                result = await self.card_repository.add_many(cards_obj.prepare_for_db())
                '''
                batch_step = MTGStockBatchStep(
                    ingestion_run_id=ingestion_run_id,
                    batch_seq=batch_number,
                    range_start=(batch_number - 1) * self.config.batch_size + 1,
                    range_end=(batch_number - 1) * self.config.batch_size + len(batch),
                    status="completed",
                    items_ok=result.successful_inserts,
                    items_failed=result.failed_inserts,
                    bytes_processed=0,
                )
                if ops_repository and ingestion_run_id:
                    await ops_repository.insert_batch_step(
                       batch_step.to_tuple()
                    )
                '''
                # Update statistics
                self.stats.successful_inserts += result.successful_inserts
                self.stats.failed_inserts += result.failed_inserts
                self.stats.batches_processed += 1

                logger.info("Batch completed", extra={"batch_number": batch_number, "inserted": result.successful_inserts, "total": len(batch)})

                # Log and queue any partial insert errors for error storage
                if result.errors:
                    for error in result.errors[:3]:
                        logger.warning("Batch insert error", extra={"batch_number": batch_number, "error": error})
                    self.failed_cards.extend([
                        {"batch": batch_number, "error": err}
                        for err in result.errors
                    ])
                
                return result
                
            except Exception as e:
                retry_count += 1
                logger.error("Batch failed", extra={"batch_number": batch_number, "attempt": retry_count, "error": str(e)})
                
                if retry_count <= self.config.max_retries:
                    wait_time = self.config.retry_delay * retry_count
                    logger.info("Retrying batch", extra={"batch_number": batch_number, "wait_seconds": wait_time})
                    await asyncio.sleep(wait_time)  # Exponential backoff
                else:
                    # Save failed batch for manual inspection
                    await self._save_failed_batch(batch, batch_number, str(e))
                    self.stats.failed_inserts += len(batch)
                    raise card_exception.CardInsertError(f"Batch {batch_number} failed after {self.config.max_retries} retries: {str(e)}")

    async def _save_failed_cards(self):
        """Save failed cards to the errors storage service for analysis"""
        if not self.failed_cards or not self.errors_storage_service:
            return
        try:
            lines_out = b"".join(
                (json.dumps(card, default=str) + "\n").encode() for card in self.failed_cards
            )
            async with self.errors_storage_service.open_stream(self.failed_cards_filename, mode="ab") as f:
                f.write(lines_out)
            logger.info("Failed cards saved", extra={"file": self.failed_cards_filename, "count": len(self.failed_cards)})
            self.failed_cards = []
        except Exception as e:
            logger.error("Failed to save failed cards", extra={"error": str(e)})

    async def _save_failed_batch(self, batch: List[card_schemas.CreateCard], batch_number: int, error: str):
        """Save a failed batch to the errors storage service for recovery"""
        if not self.errors_storage_service:
            return
        filename = f"failed_batch_{batch_number}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        try:
            batch_data = {
                "batch_number": batch_number,
                "error": error,
                "cards": [card.model_dump() for card in batch]
            }
            data = json.dumps(batch_data, indent=2, default=str).encode()
            async with self.errors_storage_service.open_stream(filename, mode="wb") as f:
                f.write(data)
            logger.info("Failed batch saved", extra={"file": filename, "batch_number": batch_number})
        except Exception as e:
            logger.error("Failed to save failed batch", extra={"batch_number": batch_number, "error": str(e)})

    def _log_processing_summary(self):
        """Log processing summary as a single structured record"""
        logger.info("Card import complete", extra=self.stats.to_dict())
