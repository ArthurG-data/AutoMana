/*
-- Customers Table
CREATE TABLE Customers (
    customer_id SERIAL PRIMARY KEY,
    organisation_or_person VARCHAR(50),
    organisation_name VARCHAR(100),
    gender VARCHAR(10),
    first_name VARCHAR(50),
    middle_initial CHAR(1),
    last_name VARCHAR(50),
    email_address VARCHAR(100) UNIQUE,
    phone_number VARCHAR(20),
    address_line_1 VARCHAR(255),
    address_line_2 VARCHAR(255),
    address_line_3 VARCHAR(255),
    address_line_4 VARCHAR(255),
    town_city VARCHAR(100),
    county VARCHAR(100),
    country VARCHAR(100)
);
*/

-- Reference: Card Conditions
CREATE TABLE IF NOT EXISTS Ref_Condition (
    condition_code SERIAL PRIMARY KEY,
    condition_description VARCHAR(10) UNIQUE NOT NULL
);


CREATE TABLE IF NOT EXISTS Collections (
    collection_id SERIAL PRIMARY KEY,
    collection_name VARCHAR(100) NOT NULL,
    user_id UUID REFERENCES users(unique_id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);


-- Collection Items (Tracks Owned Cards)
CREATE TABLE  IF NOT EXISTS CollectionItems (
    item_id UUID PRIMARY KEY,
    collection_id INT REFERENCES Collections(collection_id) ON DELETE CASCADE,
    unique_card_id UUID REFERENCES card_version(card_version_id) ON DELETE CASCADE,
    is_foil BOOLEAN DEFAULT FALSE,
    purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    purchase_price DECIMAL(10,2),  -- Using DECIMAL for better financial precision
    condition INT REFERENCES Ref_Condition(condition_code) DEFAULT 1  -- Assuming 1 = NM (Near Mint)
);

/*

-- Reference: Order Status Codes
CREATE TABLE Ref_Order_Status_Codes (
    order_status_code SERIAL PRIMARY KEY,
    order_status_description VARCHAR(50)
);

-- Orders Table
CREATE TABLE Orders (
    order_id SERIAL PRIMARY KEY,
    customer_id INT REFERENCES Customers(customer_id) ON DELETE CASCADE,
    order_status_code INT REFERENCES Ref_Order_Status_Codes(order_status_code) ON DELETE SET NULL,
    date_order_placed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    order_details TEXT
);

-- Reference: Invoice Status Codes
CREATE TABLE Ref_Invoice_Status_Codes (
    invoice_status_code SERIAL PRIMARY KEY,
    invoice_status_description VARCHAR(50)
);

-- Invoices Table
CREATE TABLE Invoices (
    invoice_number SERIAL PRIMARY KEY,
    order_id INT REFERENCES Orders(order_id) ON DELETE CASCADE,
    invoice_status_code INT REFERENCES Ref_Invoice_Status_Codes(invoice_status_code) ON DELETE SET NULL,
    invoice_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    invoice_details TEXT
);

-- Payments Table
CREATE TABLE Payments (
    payment_id SERIAL PRIMARY KEY,
    invoice_number INT REFERENCES Invoices(invoice_number) ON DELETE CASCADE,
    payment_amount DECIMAL(10,2) NOT NULL
);



-- Reference: Order Item Status Codes
CREATE TABLE Ref_Order_Item_Status_Codes (
    order_item_status_code SERIAL PRIMARY KEY,
    order_item_status_description VARCHAR(50)
);

-- Order Items Table
CREATE TABLE Order_Items (
    order_item_id SERIAL PRIMARY KEY,
    order_id INT REFERENCES Orders(order_id) ON DELETE CASCADE,
    product_id INT REFERENCES Products(product_id) ON DELETE CASCADE,
    order_item_status_code INT REFERENCES Ref_Order_Item_Status_Codes(order_item_status_code) ON DELETE SET NULL,
    order_item_quantity INT CHECK(order_item_quantity > 0),
    order_item_price DECIMAL(10,2) NOT NULL,
    RMA_number VARCHAR(50),
    RMA_issued_by VARCHAR(100),
    RMA_issued_date TIMESTAMP,
    other_order_item_details TEXT
);

-- Shipments Table
CREATE TABLE Shipments (
    shipment_id SERIAL PRIMARY KEY,
    invoice_number INT REFERENCES Invoices(invoice_number) ON DELETE CASCADE,
    shipment_tracking_number VARCHAR(50) UNIQUE,
    shipment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    other_shipment_details TEXT
);

-- Shipment Items Table (Many-to-Many Relationship Between Shipments and Order Items)
CREATE TABLE Shipment_Items (
    shipment_id INT REFERENCES Shipments(shipment_id) ON DELETE CASCADE,
    order_item_id INT REFERENCES Order_Items(order_item_id) ON DELETE CASCADE,
    PRIMARY KEY (shipment_id, order_item_id)
);
*/