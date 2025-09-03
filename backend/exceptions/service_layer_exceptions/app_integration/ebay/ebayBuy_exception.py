from typing import Optional
from backend.exceptions.service_layer_exceptions.app_integration.ebay import base_ebay_exception

class EbayBuyApiException(base_ebay_exception.EbayServiceError):
    """Base class for eBay Buy API exceptions"""
    
    def __init__(self, message: str, source_exception: Optional[Exception] = None):
        super().__init__(message, source_exception)
        self.name = "EbayBuyApiException"
    
    def __str__(self):
        return f"{self.name}: {self.message}" + (f" Source: {self.source_exception}" if self.source_exception else "")

class EbayGetItemException(EbayBuyApiException):
    """Exception raised when getting an item fails"""
    
    def __init__(self, item_id: str, message: str, source_exception: Optional[Exception] = None):
        super().__init__(f"Failed to get item {item_id}: {message}", source_exception)
        self.item_id = item_id
        self.name = "EbayGetItemException"
    
    def __str__(self):
        return f"{self.name} for Item ID {self.item_id}: {self.message}" + (f" Source: {self.source_exception}" if self.source_exception else "")
    
class EbayAddItemException(EbayBuyApiException):
    """Exception raised when adding an item fails"""
    
    def __init__(self, item_id: str, message: str, source_exception: Optional[Exception] = None):
        super().__init__(f"Failed to add item {item_id}: {message}", source_exception)
        self.item_id = item_id
        self.name = "EbayAddItemException"
    
    def __str__(self):
        return f"{self.name} for Item ID {self.item_id}: {self.message}" + (f" Source: {self.source_exception}" if self.source_exception else "")
    
class EbayReviseItemException(EbayBuyApiException): 
    """Exception raised when revising an item fails"""
    
    def __init__(self, item_id: str, message: str, source_exception: Optional[Exception] = None):
        super().__init__(f"Failed to revise item {item_id}: {message}", source_exception)
        self.item_id = item_id
        self.name = "EbayReviseItemException"
    
    def __str__(self):
        return f"{self.name} for Item ID {self.item_id}: {self.message}" + (f" Source: {self.source_exception}" if self.source_exception else "")

class EbayEndItemException(EbayBuyApiException):
    """Exception raised when ending an item fails"""
    
    def __init__(self, item_id: str, reason: str, message: str, source_exception: Optional[Exception] = None):
        super().__init__(f"Failed to end item {item_id} for reason '{reason}': {message}", source_exception)
        self.item_id = item_id
        self.reason = reason
        self.name = "EbayEndItemException"
    
    def __str__(self):
        return f"{self.name} for Item ID {self.item_id} with reason '{self.reason}': {self.message}" + (f" Source: {self.source_exception}" if self.source_exception else "")