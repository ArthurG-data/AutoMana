from pydantic import BaseModel, HttpUrl, model_validator
from typing import Optional, List, Literal

class SellerInfoType(BaseModel):
    AllowPaymentEdit: Optional[bool] = None
    CheckoutEnabled: Optional[bool] = None
    CIPBankAccountStored: Optional[bool] = None
    GoodStanding: Optional[bool] = None
    LiveAuctionAuthorized: Optional[bool] = None
    MerchandizingPref: Optional[str] = None
    QualifiesForB2BVAT: Optional[bool] = None
    StoreOwner: Optional[bool] = None
    SafePaymentExempt: Optional[bool] = None
    TopRatedSeller: Optional[bool] = None


class ReturnPolicyType(BaseModel):
    Description: Optional[str] = None
    InternationalRefundOption: Optional[str] = None
    InternationalReturnsAcceptedOption: Optional[str] = None
    InternationalReturnsWithinOption: Optional[str] = None
    InternationalShippingCostPaidByOption: Optional[str] = None
    RefundOption: Optional[str] = None
    ReturnsAcceptedOption: Optional[str] = None
    ReturnsWithinOption: Optional[str] = None
    ShippingCostPaidByOption: Optional[str] = None
class BuyerProtectionDetailsType(BaseModel): pass
class BestOfferDetailsType(BaseModel):
    BestOfferEnabled: Optional[bool] = None
    BestOfferCount: Optional[int] = None
    BestOfferStatus: Optional[str] = None  # BestOfferStatusCodeType
    BestOfferType: Optional[str] = None    # BestOfferTypeCodeType
    NewBestOffer: Optional[bool] = None
class BiddingDetailsType(BaseModel):
    ConvertedMaxBid: Optional[float] = None
    MaxBid: Optional[float] = None
    QuantityBid: Optional[int] = None
    QuantityWon: Optional[int] = None
    Winning: Optional[bool] = None
class BusinessSellerDetailsType(BaseModel):
    Email: Optional[str] = None
    Fax: Optional[str] = None
    LegalInvoice: Optional[bool] = None
    TermsAndConditions: Optional[str] = None
    TradeRegistrationNumber: Optional[str] = None
    VATPercentage: Optional[float] = None
class BuyerRequirementDetailsType(BaseModel):
    ShipToRegistrationCountry: Optional[bool] = None
    MaximumUnpaidItemStrikesInfo: Optional[dict] = None
    MaximumBuyerPolicyViolations: Optional[dict] = None
    MinimumFeedbackScore: Optional[int] = None
    LinkedPayPalAccount: Optional[bool] = None
    VerifiedUserRequirements: Optional[dict] = None
    MaximumItemRequirements: Optional[dict] = None

class CategoryType(BaseModel):
    CategoryID: str
    CategoryName: Optional[str]


class CharityType(BaseModel):
    CharityID: Optional[str] = None
    CharityName: Optional[str] = None
    DonationPercent: Optional[float] = None
class ConditionDescriptorsType(BaseModel):
    ConditionDescriptors: Optional[List[str]] = None
class CustomPoliciesType(BaseModel):
    PolicyID: Optional[str] = None
class DigitalGoodInfoType(BaseModel):
    DownloadURL: Optional[str] = None
class DiscountPriceInfoType(BaseModel):
    OriginalRetailPrice: Optional[float] = None
    PricingTreatment: Optional[str] = None
class ExtendedProducerResponsibilityType(BaseModel):
    ProducerUserID: Optional[str] = None
    ProductPackageID: Optional[str] = None
class ExtendedContactDetailsType(BaseModel):
    Name: Optional[str] = None
    Street: Optional[str] = None
    City: Optional[str] = None
    Country: Optional[str] = None
    Phone: Optional[str] = None
class ItemCompatibilityListType(BaseModel):
    CompatibilityDetails: Optional[List[dict]] = None
class ItemPolicyViolationType(BaseModel):
    PolicyID: Optional[str] = None
    PolicyText: Optional[str] = None
class ListingDetailsType(BaseModel):
    StartTime: Optional[str] = None
    EndTime: Optional[str] = None
    ViewItemURL: Optional[str] = None
class PaymentDetailsType(BaseModel):
    HoursToDeposit: Optional[int] = None
    DaysToFullPayment: Optional[int] = None
    DepositAmount: Optional[float] = None
    DepositType: Optional[str] = None
    FullPaymentDueIn: Optional[str] = None
    PaymentMethod: Optional[str] = None
class PickupInStoreDetailsType(BaseModel):
    EligibleForPickupInStore: Optional[bool] = None
class ProductListingDetailsType(BaseModel):
    UPC: Optional[str] = None
    ISBN: Optional[str] = None
    EAN: Optional[str] = None
class QuantityRestrictionPerBuyerInfoType(BaseModel):
    MaximumQuantity: Optional[int] = None
class RegulatoryType(BaseModel):
    Pictograms: Optional[List[str]] = None
    SafetyDataSheetURL: Optional[str] = None
class ReviseStatusType(BaseModel):
    ItemRevised: Optional[bool] = None
    BuyItNowAdded: Optional[bool] = None

class AddressType(BaseModel): pass
class SellerProfilesType(BaseModel):
    SellerShippingProfileID: Optional[int] = None
    SellerReturnProfileID: Optional[int] = None
    SellerPaymentProfileID: Optional[int] = None
class SellingStatusType(BaseModel):
    CurrentPrice: Optional[float] = None
    QuantitySold: Optional[int] = None
    ListingStatus: Optional[str] = None
class ShipPackageDetailsType(BaseModel):
    PackageDepth: Optional[float] = None
    PackageLength: Optional[float] = None
    PackageWidth: Optional[float] = None
    ShippingIrregular: Optional[bool] = None
class ShippingDetailsType(BaseModel):
    ShippingType: Optional[str] = None
    ShippingServiceOptions: Optional[List[dict]] = None
    InternationalShippingServiceOption: Optional[List[dict]] = None
    SalesTax: Optional[dict] = None
    ShippingServiceUsed: Optional[str] = None
    PaymentInstructions: Optional[str] = None
    ShippingDiscountProfileID: Optional[str] = None

class ShippingServiceCostOverrideListType(BaseModel):
    CostOverrideList: Optional[List[dict]] = None
class StorefrontType(BaseModel):
    StoreCategoryID: Optional[int] = None
    StoreURL: Optional[str] = None
class UnitInfoType(BaseModel):
    UnitType: Optional[str] = None
    UnitQuantity: Optional[float] = None
class VariationsType(BaseModel):
    VariationList: Optional[List[dict]] = None
class VATDetailsType(BaseModel):
    VATPercent: Optional[float] = None
    VATSite: Optional[str] = None
    VATID: Optional[str] = None
class VideoDetailsType(BaseModel):
    VideoURL: Optional[str] = None
    VideoID: Optional[str] = None

class ShipPackageDetailsType(BaseModel):
    PackageDepth: Optional[float] = None
    PackageLength: Optional[float] = None
    PackageWidth: Optional[float] = None
    ShippingIrregular: Optional[bool] = None
    ShippingPackage: Optional[str] = None
    WeightMajor: Optional[float] = None
    WeightMinor: Optional[float] = None

class ListingDetailsType(BaseModel):
    StartTime: Optional[str] = None
    EndTime: Optional[str] = None
    ViewItemURL: Optional[str] = None
    ConvertedStartPrice: Optional[float] = None
    ConvertedReservePrice: Optional[float] = None
    ConvertedBuyItNowPrice: Optional[float] = None
    MinimumBestOfferPrice: Optional[float] = None
    ViewItemURLForNaturalSearch: Optional[str] = None

class ConditionDescriptorsType(BaseModel):
    ConditionDescriptors: Optional[List[str]] = None

class UserType(BaseModel):
    AboutMePage: Optional[bool] = None
    Email: Optional[str] = None
    FeedbackScore: Optional[int] = None
    PositiveFeedbackPercent: Optional[float] = None
    FeedbackPrivate: Optional[bool] = None
    IDVerified: Optional[bool] = None
    eBayGoodStanding: Optional[bool] = None
    NewUser: Optional[bool] = None
    RegistrationDate: Optional[str] = None
    Site: Optional[str] = None
    Status: Optional[str] = None
    UserID: Optional[str] = None
    UserIDChanged: Optional[bool] = None
    VATStatus: Optional[str] = None
    SellerInfo: Optional[SellerInfoType] = None
    MotorsDealer: Optional[bool] = None

class ItemModel(BaseModel):
    Title: Optional[str] = None
    Description: Optional[str] = None
    ApplicationData: Optional[str] = None
    ApplyBuyerProtection: Optional[BuyerProtectionDetailsType] = None
    AutoPay: Optional[bool] = None
    AvailableForPickupDropOff: Optional[bool] = None
    BestOfferDetails: Optional[BestOfferDetailsType] = None
    BiddingDetails: Optional[BiddingDetailsType] = None
    BusinessSellerDetails: Optional[BusinessSellerDetailsType] = None
    BuyerGuaranteePrice: Optional[float] = None
    BuyerProtection: Optional[str] = None
    BuyerRequirementDetails: Optional[BuyerRequirementDetailsType] = None
    BuyerResponsibleForShipping: Optional[bool] = None
    BuyItNowPrice: Optional[float] = None
    CategoryMappingAllowed: Optional[bool] = None
    CeilingPrice: Optional[float] = None
    Charity: Optional[CharityType] = None
    ClassifiedAdPayPerLeadFee: Optional[float] = None
    ConditionDefinition: Optional[str] = None
    ConditionDescription: Optional[str] = None
    ConditionDescriptors: Optional[ConditionDescriptorsType] = None
    ConditionDisplayName: Optional[str] = None
    ConditionID: Optional[int] = None
    Country: Optional[str] = None
    CrossBorderTrade: Optional[str] = None
    Currency: Optional[str] = None
    CustomPolicies: Optional[CustomPoliciesType] = None
    DescriptionReviseMode: Optional[str] = None
    DigitalGoodInfo: Optional[DigitalGoodInfoType] = None
    DisableBuyerRequirements: Optional[bool] = None
    DiscountPriceInfo: Optional[DiscountPriceInfoType] = None
    DispatchTimeMax: Optional[int] = None
    eBayNotes: Optional[str] = None
    eBayPlus: Optional[bool] = None
    eBayPlusEligible: Optional[bool] = None
    EligibleForPickupDropOff: Optional[bool] = None
    eMailDeliveryAvailable: Optional[bool] = None
    ExtendedProducerResponsibility: Optional[ExtendedProducerResponsibilityType] = None
    ExtendedSellerContactDetails: Optional[ExtendedContactDetailsType] = None
    FloorPrice: Optional[float] = None
    FreeAddedCategory: Optional[str] = None
    GetItFast: Optional[bool] = None
    HideFromSearch: Optional[bool] = None
    HitCount: Optional[int] = None
    IgnoreQuantity: Optional[bool] = None
    IntegratedMerchantCreditCardEnabled: Optional[bool] = None
    InventoryTrackingMethod: Optional[str] = None
    IsIntermediatedShippingEligible: Optional[bool] = None
    IsItemEMSEligible: Optional[bool] = None
    IsSecureDescription: Optional[bool] = None
    ItemCompatibilityCount: Optional[int] = None
    ItemCompatibilityList: Optional[ItemCompatibilityListType] = None
    ItemID: Optional[str] = None
    ItemPolicyViolation: Optional[ItemPolicyViolationType] = None
    ItemSpecifics: Optional[dict] = None
    LeadCount: Optional[int] = None
    ListingDetails: Optional[ListingDetailsType] = None
    ListingDuration: Optional[str] = None
    ListingEnhancement: Optional[str] = None
    ListingSubtype2: Optional[str] = None
    ListingType: Optional[str] = None
    Location: Optional[str] = None
    LocationDefaulted: Optional[bool] = None
    LotSize: Optional[int] = None
    MechanicalCheckAccepted: Optional[bool] = None
    NewLeadCount: Optional[int] = None
    PaymentAllowedSite: Optional[str] = None
    PaymentDetails: Optional[PaymentDetailsType] = None
    PaymentMethods: Optional[List[str]] = None
    PayPalEmailAddress: Optional[str] = None
    PickupInStoreDetails: Optional[PickupInStoreDetailsType] = None
    PictureDetails: Optional[dict] = None
    PostalCode: Optional[str] = None
    PrimaryCategory: Optional[CategoryType] = None
    PrivateListing: Optional[bool] = None
    PrivateNotes: Optional[str] = None
    ProductListingDetails: Optional[ProductListingDetailsType] = None
    ProxyItem: Optional[bool] = None
    Quantity: Optional[int] = None
    QuantityAvailable: Optional[int] = None
    QuantityAvailableHint: Optional[str] = None
    QuantityRestrictionPerBuyer: Optional[QuantityRestrictionPerBuyerInfoType] = None
    QuantityThreshold: Optional[int] = None
    QuestionCount: Optional[int] = None
    ReasonHideFromSearch: Optional[str] = None
    Regulatory: Optional[RegulatoryType] = None
    Relisted: Optional[bool] = None
    RelistLink: Optional[bool] = None
    RelistParentID: Optional[int] = None
    ReservePrice: Optional[float] = None
    ReturnPolicy: Optional[ReturnPolicyType] = None
    ReviseStatus: Optional[ReviseStatusType] = None
    ScheduleTime: Optional[str] = None
    SecondaryCategory: Optional[CategoryType] = None
    Seller: Optional[UserType] = None
    SellerContactDetails: Optional[AddressType] = None
    SellerProfiles: Optional[SellerProfilesType] = None
    SellerProvidedTitle: Optional[str] = None
    SellerVacationNote: Optional[str] = None
    SellingStatus: Optional[SellingStatusType] = None
    ShippingDetails: Optional[ShippingDetailsType] = None
    #ShippingPackageDetails: Optional[ShipPackageDetailsType] = None
    ShippingServiceCostOverrideList: Optional[ShippingServiceCostOverrideListType] = None
    ShipToLocations: Optional[str] = None
    Site: Optional[str] = None
    SKU: Optional[str] = None
    StartPrice: Optional[float] = None
    Storefront: Optional[StorefrontType] = None
    SubTitle: Optional[str] = None
    TaxCategory: Optional[str] = None
    TimeLeft: Optional[str] = None
    TopRatedListing: Optional[bool] = None
    TotalQuestionCount: Optional[int] = None
    UnitInfo: Optional[UnitInfoType] = None
    UseTaxTable: Optional[bool] = None
    UUID: Optional[str] = None
    Variations: Optional[VariationsType] = None
    VATDetails: Optional[VATDetailsType] = None
    VideoDetails: Optional[VideoDetailsType] = None
    VIN: Optional[str] = None
    VINLink: Optional[str] = None
    VRM: Optional[str] = None
    VRMLink: Optional[str] = None
    WatchCount: Optional[int] = None


class ActiveListing(BaseModel):
    item_id: str
    title: str
    buy_it_now_price: float
    currency: str
    start_time: str
    time_left: str
    quantity: int
    quantity_available: int
    current_price: float
    view_url: HttpUrl
    image_url: Optional[HttpUrl]
    
class ActiveListingResponse(BaseModel):
    item_number : Optional[int]=None
    items : List[ActiveListing|None]
    @model_validator(mode='after')
    def set_item_number(self) -> "ActiveListingResponse":
        self.item_number = len(self.items)
        return self

class CardListing(BaseModel):
    title: str
    description: str
    price: float
    image_url: HttpUrl
    postal_code: str
    condition_id: Literal[1000, 3000, 4000] = 4000  # 1000: New, 3000: Used, 4000: Like New
    category_id: str = "183454"
    shipping_cost: float = 2.50
    site: str = "AU"


class ListingUpdate(BaseModel):
    item_id : str
    price: Optional[float]=None
    pictures: Optional[List[HttpUrl]] =None