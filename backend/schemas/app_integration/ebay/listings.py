from pydantic import BaseModel, ConfigDict, HttpUrl, model_validator, Field
from typing import Optional, List, Literal

class SellerInfoType(BaseModel):
    AllowPaymentEdit: Optional[bool] = Field(None, alias="allowPaymentEdit")
    CheckoutEnabled: Optional[bool] = Field(None, alias="checkoutEnabled")
    CIPBankAccountStored: Optional[bool] = Field(None, alias="cipBankAccountStored")
    GoodStanding: Optional[bool] = Field(None, alias="goodStanding")
    LiveAuctionAuthorized: Optional[bool] = Field(None, alias="liveAuctionAuthorized")
    MerchandizingPref: Optional[str] = Field(None, alias="merchandizingPref")
    QualifiesForB2BVAT: Optional[bool] = Field(None, alias="qualifiesForB2BVAT")
    StoreOwner: Optional[bool] = Field(None, alias="storeOwner")
    SafePaymentExempt: Optional[bool] = Field(None, alias="safePaymentExempt")
    TopRatedSeller: Optional[bool] = Field(None, alias="topRatedSeller")

class BaseCostType(BaseModel):
    currencyID: Optional[str] = Field(None, alias="currency")
    text: Optional[str | float] = Field(None, alias="value")

class ReturnPolicyType(BaseModel):
    Description: Optional[str] = Field(None, alias="description")
    InternationalRefundOption: Optional[str] = Field(None, alias="internationalRefundOption")
    InternationalReturnsAcceptedOption: Optional[str] = Field(None, alias="internationalReturnsAcceptedOption")
    InternationalReturnsWithinOption: Optional[str] = Field(None, alias="internationalReturnsWithinOption")
    InternationalShippingCostPaidByOption: Optional[str] = Field(None, alias="internationalShippingCostPaidByOption")
    RefundOption: Optional[str] = Field(None, alias="refundOption")
    ReturnsAcceptedOption: Optional[str] = Field(None, alias="returnsAcceptedOption")
    ReturnsWithinOption: Optional[str] = Field(None, alias="returnsWithinOption")
    ShippingCostPaidByOption: Optional[str] = Field(None, alias="shippingCostPaidByOption")


class BuyerProtectionDetailsType(BaseModel): pass

class BestOfferDetailsType(BaseModel):
    BestOfferEnabled: Optional[bool] = Field(None, alias="bestOfferEnabled")
    BestOfferCount: Optional[int] = Field(None, alias="bestOfferCount")
    BestOfferStatus: Optional[str] = Field(None, alias="bestOfferStatus")
    BestOfferType: Optional[str] = Field(None, alias="bestOfferType")
    NewBestOffer: Optional[bool] = Field(None, alias="newBestOffer")

class BiddingDetailsType(BaseModel):
    ConvertedMaxBid: Optional[float] = Field(None, alias="convertedMaxBid")
    MaxBid: Optional[float] = Field(None, alias="maxBid")
    QuantityBid: Optional[int] = Field(None, alias="quantityBid")
    QuantityWon: Optional[int] = Field(None, alias="quantityWon")
    Winning: Optional[bool] = Field(None, alias="winning")
    
class BusinessSellerDetailsType(BaseModel):
    Email: Optional[str] = Field(None, alias="email")
    Fax: Optional[str] = Field(None, alias="fax")
    LegalInvoice: Optional[bool] = Field(None, alias="legalInvoice")
    TermsAndConditions: Optional[str] = Field(None, alias="termsAndConditions")
    TradeRegistrationNumber: Optional[str] = Field(None, alias="tradeRegistrationNumber")
    VATPercentage: Optional[float] = Field(None, alias="vatPercentage")

class BuyerRequirementDetailsType(BaseModel):
    ShipToRegistrationCountry: Optional[bool] = Field(None, alias="shipToRegistrationCountry")
    MaximumUnpaidItemStrikesInfo: Optional[dict] = Field(None, alias="maximumUnpaidItemStrikesInfo")
    MaximumBuyerPolicyViolations: Optional[dict] = Field(None, alias="maximumBuyerPolicyViolations")
    MinimumFeedbackScore: Optional[int] = Field(None, alias="minimumFeedbackScore")
    LinkedPayPalAccount: Optional[bool] = Field(None, alias="linkedPayPalAccount")
    VerifiedUserRequirements: Optional[dict] = Field(None, alias="verifiedUserRequirements")
    MaximumItemRequirements: Optional[dict] = Field(None, alias="maximumItemRequirements")


class CategoryType(BaseModel):
    CategoryID: str = Field(alias="categoryId")
    CategoryName: Optional[str] = Field(None, alias="categoryName")


class CharityType(BaseModel):
    CharityID: Optional[str] = Field(None, alias="charityId")
    CharityName: Optional[str] = Field(None, alias="charityName")
    DonationPercent: Optional[float] = Field(None, alias="donationPercent")

class ConditionDescriptorsType(BaseModel):
    ConditionDescriptors: Optional[List[str]] = Field(None, alias="conditionDescriptors")


class CustomPoliciesType(BaseModel):
    PolicyID: Optional[str] = Field(None, alias="policyId")

class DigitalGoodInfoType(BaseModel):
    DownloadURL: Optional[str] = Field(None, alias="downloadUrl")

class DiscountPriceInfoType(BaseModel):
    OriginalRetailPrice: Optional[BaseCostType] = Field(None, alias="originalRetailPrice")
    PricingTreatment: Optional[str] = Field(None, alias="pricingTreatment")

class ExtendedProducerResponsibilityType(BaseModel):
    ProducerUserID: Optional[str] = Field(None, alias="producerUserId")
    ProductPackageID: Optional[str] = Field(None, alias="productPackageId")

class ExtendedContactDetailsType(BaseModel):
    Name: Optional[str] = Field(None, alias="name")
    Street: Optional[str] = Field(None, alias="street")
    City: Optional[str] = Field(None, alias="city")
    Country: Optional[str] = Field(None, alias="country")
    Phone: Optional[str] = Field(None, alias="phone")

class ItemCompatibilityListType(BaseModel):
    CompatibilityDetails: Optional[List[dict]] = Field(None, alias="compatibilityDetails")

class ItemPolicyViolationType(BaseModel):
    PolicyID: Optional[str] = Field(None, alias="policyId")
    PolicyText: Optional[str] = Field(None, alias="policyText")
    
class ListingDetailsType(BaseModel):
    StartTime: Optional[str] = Field(None, alias="startTime")
    EndTime: Optional[str] = Field(None, alias="endTime")
    ViewItemURL: Optional[str] = Field(None, alias="viewItemUrl")
    ConvertedStartPrice: Optional[BaseCostType] = Field(None, alias="convertedStartPrice")
    ConvertedReservePrice: Optional[BaseCostType] = Field(None, alias="convertedReservePrice")
    ConvertedBuyItNowPrice: Optional[BaseCostType] = Field(None, alias="convertedBuyItNowPrice")
    MinimumBestOfferPrice: Optional[BaseCostType] = Field(None, alias="minimumBestOfferPrice")
    ViewItemURLForNaturalSearch: Optional[str] = Field(None, alias="viewItemUrlForNaturalSearch")


class PaymentDetailsType(BaseModel):
    HoursToDeposit: Optional[int] = Field(None, alias="hoursToDeposit")
    DaysToFullPayment: Optional[int] = Field(None, alias="daysToFullPayment")
    DepositAmount: Optional[float] = Field(None, alias="depositAmount")
    DepositType: Optional[str] = Field(None, alias="depositType")
    FullPaymentDueIn: Optional[str] = Field(None, alias="fullPaymentDueIn")
    PaymentMethod: Optional[str] = Field(None, alias="paymentMethod")

class PickupInStoreDetailsType(BaseModel):
    EligibleForPickupInStore: Optional[bool] = Field(None, alias="eligibleForPickupInStore")

class ProductListingDetailsType(BaseModel):
    UPC: Optional[str] = Field(None, alias="upc")
    ISBN: Optional[str] = Field(None, alias="isbn")
    EAN: Optional[str] = Field(None, alias="ean")

class QuantityRestrictionPerBuyerInfoType(BaseModel):
    MaximumQuantity: Optional[int] = Field(None, alias="maximumQuantity")

class RegulatoryType(BaseModel):
    Pictograms: Optional[List[str]] = Field(None, alias="pictograms")
    SafetyDataSheetURL: Optional[str] = Field(None, alias="safetyDataSheetUrl")

class ReviseStatusType(BaseModel):
    ItemRevised: Optional[bool] = Field(None, alias="itemRevised")
    BuyItNowAdded: Optional[bool] = Field(None, alias="buyItNowAdded")


class AddressType(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
class SellerProfilesType(BaseModel):
    SellerShippingProfileID: Optional[int] = Field(None, alias="sellerShippingProfileId")
    SellerReturnProfileID: Optional[int] = Field(None, alias="sellerReturnProfileId")
    SellerPaymentProfileID: Optional[int] = Field(None, alias="sellerPaymentProfileId")

class SellingStatusType(BaseModel):
    CurrentPrice: Optional[BaseCostType] = Field(None, alias="currentPrice")
    QuantitySold: Optional[int] = Field(None, alias="quantitySold")
    ListingStatus: Optional[str] = Field(None, alias="listingStatus")

class ShipPackageDetailsType(BaseModel):
    PackageDepth: Optional[float] = Field(None, alias="packageDepth")
    PackageLength: Optional[float] = Field(None, alias="packageLength")
    PackageWidth: Optional[float] = Field(None, alias="packageWidth")
    ShippingIrregular: Optional[bool] = Field(None, alias="shippingIrregular")
    ShippingPackage: Optional[str] = Field(None, alias="shippingPackage")
    WeightMajor: Optional[float] = Field(None, alias="weightMajor")
    WeightMinor: Optional[float] = Field(None, alias="weightMinor")


class ShippingServiceOptionType(BaseModel):
    ShippingService: Optional[str] = Field(None, alias="shippingService")
    ShippingServiceCost: Optional[BaseCostType] = Field(None, alias="shippingServiceCost")
    ShippingServicePriority: Optional[int] = Field(None, alias="shippingServicePriority")
    ExpeditedService: Optional[bool] = Field(None, alias="expeditedService")
    ShippingTimeMin: Optional[int] = Field(None, alias="shippingTimeMin")
    ShippingTimeMax: Optional[int] = Field(None, alias="shippingTimeMax")


class ShippingDetailsType(BaseModel):
    ShippingType: Optional[str] = Field(None, alias="shippingType")
    ShippingServiceOptions: Optional[List[ShippingServiceOptionType] | ShippingServiceOptionType] = Field(None, alias="shippingServiceOptions")
    InternationalShippingServiceOption: Optional[List[dict]] = Field(None, alias="internationalShippingServiceOption")
    SalesTax: Optional[dict] = Field(None, alias="salesTax")
    ShippingServiceUsed: Optional[str] = Field(None, alias="shippingServiceUsed")
    PaymentInstructions: Optional[str] = Field(None, alias="paymentInstructions")
    ShippingDiscountProfileID: Optional[str] = Field(None, alias="shippingDiscountProfileId")


class SalesTaxType(BaseModel):
    SalesTaxPercent: Optional[float] = Field(None, alias="salesTaxPercent")
    ShippingIncludedInTax: Optional[bool] = Field(None, alias="shippingIncludedInTax")

class ShippingServiceCostOverrideListType(BaseModel):
    CostOverrideList: Optional[List[dict]] = Field(None, alias="costOverrideList")

class StorefrontType(BaseModel):
    StoreCategoryID: Optional[int] = Field(None, alias="storeCategoryId")
    StoreURL: Optional[str] = Field(None, alias="storeUrl")

class UnitInfoType(BaseModel):
    UnitType: Optional[str] = Field(None, alias="unitType")
    UnitQuantity: Optional[float] = Field(None, alias="unitQuantity")
class VariationsType(BaseModel):
    VariationList: Optional[List[dict]] = Field(None, alias="variationList")

class VATDetailsType(BaseModel):
    VATPercent: Optional[float] = Field(None, alias="vatPercent")
    VATSite: Optional[str] = Field(None, alias="vatSite")
    VATID: Optional[str] = Field(None, alias="vatId")

class VideoDetailsType(BaseModel):
    VideoURL: Optional[str] = Field(None, alias="videoUrl")
    VideoID: Optional[str] = Field(None, alias="videoId")

class ShipPackageDetailsType(BaseModel):
    PackageDepth: Optional[float] = Field(None, alias="packageDepth")
    PackageLength: Optional[float] = Field(None, alias="packageLength")
    PackageWidth: Optional[float] = Field(None, alias="packageWidth")
    ShippingIrregular: Optional[bool] = Field(None, alias="shippingIrregular")
    ShippingPackage: Optional[str] = Field(None, alias="shippingPackage")
    WeightMajor: Optional[float] = Field(None, alias="weightMajor")
    WeightMinor: Optional[float] = Field(None, alias="weightMinor")

class ListingDetailsType(BaseModel):
    StartTime: Optional[str] = Field(None, alias="startTime")
    EndTime: Optional[str] = Field(None, alias="endTime")
    ViewItemURL: Optional[str] = Field(None, alias="viewItemUrl")
    ConvertedStartPrice: Optional[BaseCostType] = Field(None, alias="convertedStartPrice")
    ConvertedReservePrice: Optional[BaseCostType] = Field(None, alias="convertedReservePrice")
    ConvertedBuyItNowPrice: Optional[BaseCostType] = Field(None, alias="convertedBuyItNowPrice")
    MinimumBestOfferPrice: Optional[BaseCostType] = Field(None, alias="minimumBestOfferPrice")
    ViewItemURLForNaturalSearch: Optional[str] = Field(None, alias="viewItemUrlForNaturalSearch")

class ConditionDescriptorsType(BaseModel):
    ConditionDescriptors: Optional[List[str]] = Field(None, alias="conditionDescriptors")

class UserType(BaseModel):
    AboutMePage: Optional[bool] = Field(None, alias="aboutMePage")
    Email: Optional[str] = Field(None, alias="email")
    FeedbackScore: Optional[int] = Field(None, alias="feedbackScore")
    PositiveFeedbackPercent: Optional[float] = Field(None, alias="positiveFeedbackPercent")
    FeedbackPrivate: Optional[bool] = Field(None, alias="feedbackPrivate")
    IDVerified: Optional[bool] = Field(None, alias="idVerified")
    eBayGoodStanding: Optional[bool] = Field(None, alias="eBayGoodStanding")
    NewUser: Optional[bool] = Field(None, alias="newUser")
    RegistrationDate: Optional[str] = Field(None, alias="registrationDate")
    Site: Optional[str] = Field(None, alias="site")
    Status: Optional[str] = Field(None, alias="status")
    UserID: Optional[str] = Field(None, alias="userID")
    UserIDChanged: Optional[bool] = Field(None, alias="userIDChanged")
    VATStatus: Optional[str] = Field(None, alias="vatStatus")
    SellerInfo: Optional[SellerInfoType] = Field(None, alias="sellerInfo")
    MotorsDealer: Optional[bool] = Field(None, alias="motorsDealer")

class ItemModel(BaseModel):
    Title: Optional[str] = Field(None, alias="title")
    Description: Optional[str] = Field(None, alias="description")
    ApplicationData: Optional[str] = Field(None, alias="applicationData")
    ApplyBuyerProtection: Optional[BuyerProtectionDetailsType] = Field(None, alias="applyBuyerProtection")
    AutoPay: Optional[bool] = Field(None, alias="autoPay")
    AvailableForPickupDropOff: Optional[bool] = Field(None, alias="availableForPickupDropOff")
    BestOfferDetails: Optional[BestOfferDetailsType] = Field(None, alias="bestOfferDetails")
    BiddingDetails: Optional[BiddingDetailsType] = Field(None, alias="biddingDetails")
    BusinessSellerDetails: Optional[BusinessSellerDetailsType] = Field(None, alias="businessSellerDetails")
    BuyerGuaranteePrice: Optional[BaseCostType] = Field(None, alias="buyerGuaranteePrice")
    BuyerProtection: Optional[str] = Field(None, alias="buyerProtection")
    BuyerRequirementDetails: Optional[BuyerRequirementDetailsType] = Field(None, alias="buyerRequirementDetails")
    BuyerResponsibleForShipping: Optional[bool] = Field(None, alias="buyerResponsibleForShipping")
    BuyItNowPrice: Optional[BaseCostType] = Field(None, alias="buyItNowPrice")
    CategoryMappingAllowed: Optional[bool] = Field(None, alias="categoryMappingAllowed")
    CeilingPrice: Optional[BaseCostType] = Field(None, alias="ceilingPrice")
    Charity: Optional[CharityType] = Field(None, alias="charity")
    ClassifiedAdPayPerLeadFee: Optional[BaseCostType] = Field(None, alias="classifiedAdPayPerLeadFee")
    ConditionDefinition: Optional[str] = Field(None, alias="conditionDefinition")
    ConditionDescription: Optional[str] = Field(None, alias="conditionDescription")
    ConditionDescriptors: Optional[ConditionDescriptorsType] = Field(None, alias="conditionDescriptors")
    ConditionDisplayName: Optional[str] = Field(None, alias="conditionDisplayName")
    ConditionID: Optional[int] = Field(None, alias="conditionID")
    Country: Optional[str] = Field(None, alias="country")
    CrossBorderTrade: Optional[str] = Field(None, alias="crossBorderTrade")
    Currency: Optional[str] = Field(None, alias="currency")
    CustomPolicies: Optional[CustomPoliciesType] = Field(None, alias="customPolicies")
    DescriptionReviseMode: Optional[str] = Field(None, alias="descriptionReviseMode")
    DigitalGoodInfo: Optional[DigitalGoodInfoType] = Field(None, alias="digitalGoodInfo")
    DisableBuyerRequirements: Optional[bool] = Field(None, alias="disableBuyerRequirements")
    DiscountPriceInfo: Optional[DiscountPriceInfoType] = Field(None, alias="discountPriceInfo")
    DispatchTimeMax: Optional[int] = Field(None, alias="dispatchTimeMax")
    eBayNotes: Optional[str] = Field(None, alias="eBayNotes")
    eBayPlus: Optional[bool] = Field(None, alias="eBayPlus")
    eBayPlusEligible: Optional[bool] = Field(None, alias="eBayPlusEligible")
    EligibleForPickupDropOff: Optional[bool] = Field(None, alias="eligibleForPickupDropOff")
    eMailDeliveryAvailable: Optional[bool] = Field(None, alias="eMailDeliveryAvailable")
    ExtendedProducerResponsibility: Optional[ExtendedProducerResponsibilityType] = Field(None, alias="extendedProducerResponsibility")
    ExtendedSellerContactDetails: Optional[ExtendedContactDetailsType] = Field(None, alias="extendedSellerContactDetails")
    FloorPrice: Optional[BaseCostType] = Field(None, alias="floorPrice")
    FreeAddedCategory: Optional[str] = Field(None, alias="freeAddedCategory")
    GetItFast: Optional[bool] = Field(None, alias="getItFast")
    HasUnansweredQuestions : Optional[bool] = Field(None, alias="hasUnansweredQuestions")
    HasPublicMessages : Optional[bool] = Field(None, alias="hasPublicMessages")
    HideFromSearch: Optional[bool] = Field(None, alias="hideFromSearch")
    HitCount: Optional[int] = Field(None, alias="hitCount")
    IgnoreQuantity: Optional[bool] = Field(None, alias="ignoreQuantity")
    IntegratedMerchantCreditCardEnabled: Optional[bool] = Field(None, alias="integratedMerchantCreditCardEnabled")
    InventoryTrackingMethod: Optional[str] = Field(None, alias="inventoryTrackingMethod")
    IsIntermediatedShippingEligible: Optional[bool] = Field(None, alias="isIntermediatedShippingEligible")
    IsItemEMSEligible: Optional[bool] = Field(None, alias="isItemEMSEligible")
    IsSecureDescription: Optional[bool] = Field(None, alias="isSecureDescription")
    ItemCompatibilityCount: Optional[int] = Field(None, alias="itemCompatibilityCount")
    ItemCompatibilityList: Optional[ItemCompatibilityListType] = Field(None, alias="itemCompatibilityList")
    ItemID: Optional[str] = Field(None, alias="itemID")
    ItemPolicyViolation: Optional[ItemPolicyViolationType] = Field(None, alias="itemPolicyViolation")
    ItemSpecifics: Optional[dict] = Field(None, alias="itemSpecifics")
    LeadCount: Optional[int] = Field(None, alias="leadCount")
    ListingDetails: Optional[ListingDetailsType] = Field(None, alias="listingDetails")
    ListingDuration: Optional[str] = Field(None, alias="listingDuration")
    ListingEnhancement: Optional[str] = Field(None, alias="listingEnhancement")
    ListingSubtype2: Optional[str] = Field(None, alias="listingSubtype2")
    ListingType: Optional[str] = Field(None, alias="listingType")
    Location: Optional[str] = Field(None, alias="location")
    LocationDefaulted: Optional[bool] = Field(None, alias="locationDefaulted")
    LotSize: Optional[int] = Field(None, alias="lotSize")
    MechanicalCheckAccepted: Optional[bool] = Field(None, alias="mechanicalCheckAccepted")
    NewLeadCount: Optional[int] = Field(None, alias="newLeadCount")
    PaymentAllowedSite: Optional[str] = Field(None, alias="paymentAllowedSite")
    PaymentDetails: Optional[PaymentDetailsType] = Field(None, alias="paymentDetails")
    PaymentMethods: Optional[List[str]] = Field(None, alias="paymentMethods")
    PayPalEmailAddress: Optional[str] = Field(None, alias="payPalEmailAddress")
    PickupInStoreDetails: Optional[PickupInStoreDetailsType] = Field(None, alias="pickupInStoreDetails")
    PictureDetails: Optional[dict] = Field(None, alias="pictureDetails")
    PostalCode: Optional[str] = Field(None, alias="postalCode")
    PrimaryCategory: Optional[CategoryType] = Field(None, alias="primaryCategory")
    PrivateListing: Optional[bool] = Field(None, alias="privateListing")
    PrivateNotes: Optional[str] = Field(None, alias="privateNotes")
    ProductListingDetails: Optional[ProductListingDetailsType] = Field(None, alias="productListingDetails")
    ProxyItem: Optional[bool] = Field(None, alias="proxyItem")
    Quantity: Optional[int] = Field(None, alias="quantity")
    QuantityAvailable: Optional[int] = Field(None, alias="quantityAvailable")
    QuantityAvailableHint: Optional[str] = Field(None, alias="quantityAvailableHint")
    QuantityRestrictionPerBuyer: Optional[QuantityRestrictionPerBuyerInfoType] = Field(None, alias="quantityRestrictionPerBuyer")
    QuantityThreshold: Optional[int] = Field(None, alias="quantityThreshold")
    QuestionCount: Optional[int] = Field(None, alias="questionCount")
    ReasonHideFromSearch: Optional[str] = Field(None, alias="reasonHideFromSearch")
    Regulatory: Optional[RegulatoryType] = Field(None, alias="regulatory")
    Relisted: Optional[bool] = Field(None, alias="relisted")
    RelistLink: Optional[bool] = Field(None, alias="relistLink")
    RelistParentID: Optional[int] = Field(None, alias="relistParentID")
    ReservePrice: Optional[BaseCostType] = Field(None, alias="reservePrice")
    ReturnPolicy: Optional[ReturnPolicyType] = Field(None, alias="returnPolicy")
    ReviseStatus: Optional[ReviseStatusType] = Field(None, alias="reviseStatus")
    ScheduleTime: Optional[str] = Field(None, alias="scheduleTime")
    SecondaryCategory: Optional[CategoryType] = Field(None, alias="secondaryCategory")
    Seller: Optional[UserType] = Field(None, alias="seller")
    SellerContactDetails: Optional[AddressType] = Field(None, alias="sellerContactDetails")
    SellerProfiles: Optional[SellerProfilesType] = Field(None, alias="sellerProfiles")
    SellerProvidedTitle: Optional[str] = Field(None, alias="sellerProvidedTitle")
    SellerVacationNote: Optional[str] = Field(None, alias="sellerVacationNote")
    SellingStatus: Optional[SellingStatusType] = Field(None, alias="sellingStatus")
    ShippingDetails: Optional[ShippingDetailsType] = Field(None, alias="shippingDetails")
    #ShippingPackageDetails: Optional[ShipPackageDetailsType] = None
    ShippingServiceCostOverrideList: Optional[ShippingServiceCostOverrideListType] = Field(None, alias="shippingServiceCostOverrideList")
    ShipToLocations: Optional[str] = Field(None, alias="shipToLocations")
    Site: Optional[str] = Field(None, alias="site")
    SKU: Optional[str] = Field(None, alias="sku")
    StartPrice: Optional[BaseCostType] = Field(None, alias="startPrice")
    Storefront: Optional[StorefrontType] = Field(None, alias="storefront")
    SubTitle: Optional[str] = Field(None, alias="subTitle")
    TaxCategory: Optional[str] = Field(None, alias="taxCategory")
    TimeLeft: Optional[str] = Field(None, alias="timeLeft")
    TopRatedListing: Optional[bool] = Field(None, alias="topRatedListing")
    TotalQuestionCount: Optional[int] = Field(None, alias="totalQuestionCount")
    UnitInfo: Optional[UnitInfoType] = Field(None, alias="unitInfo")
    UseTaxTable: Optional[bool] = Field(None, alias="useTaxTable")
    UUID: Optional[str] = Field(None, alias="uuid")
    Variations: Optional[VariationsType] = Field(None, alias="variations")
    VATDetails: Optional[VATDetailsType] = Field(None, alias="vatDetails")
    VideoDetails: Optional[VideoDetailsType] = Field(None, alias="videoDetails")
    VIN: Optional[str] = Field(None, alias="vin")
    VINLink: Optional[str] = Field(None, alias="vinLink")
    VRM: Optional[str] = Field(None, alias="vrm")
    VRMLink: Optional[str] = Field(None, alias="vrmLink")
    WatchCount: Optional[int] = Field(None, alias="watchCount")

    model_config = ConfigDict(populate_by_name=True, extra="allow")

class SearchResult(BaseModel):
    href: str
    total: int
    offset: int
    itemSummaries : Optional[List[ItemModel]|None] = None

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    
    def __iter__(self):
        return iter(self.itemSummaries)
    def __len__(self):
        return len(self.itemSummaries) if self.itemSummaries else 0
    def __next__(self):
        return next(iter(self.itemSummaries))
    def __getitem__(self, index: int) -> Optional[ItemModel]:
        if self.itemSummaries:
            return self.itemSummaries[index]
        return None

class ActiveListingResponse(BaseModel):
    item_number : Optional[int]=None
    items : List[ItemModel|None]

    
    @model_validator(mode='after')
    def set_item_number(self) -> "ActiveListingResponse":
        self.item_number = len(self.items)
        return self
