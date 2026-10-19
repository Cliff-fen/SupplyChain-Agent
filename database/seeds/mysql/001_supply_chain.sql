-- MySQL 8+ equivalent teaching source schema. Execute in a dedicated source DB.
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS suppliers (
  supplier_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  supplier_code VARCHAR(40) NOT NULL UNIQUE,
  supplier_name VARCHAR(160) NOT NULL,
  region VARCHAR(80) NOT NULL
);
CREATE TABLE IF NOT EXISTS materials (
  material_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  material_code VARCHAR(40) NOT NULL UNIQUE,
  material_name VARCHAR(160) NOT NULL,
  product_line VARCHAR(80) NOT NULL,
  safety_stock DECIMAL(14,2) NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS production_work_orders (
  work_order_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  order_number VARCHAR(40) NOT NULL UNIQUE,
  factory VARCHAR(80) NOT NULL,
  product_line VARCHAR(80) NOT NULL,
  planned_quantity DECIMAL(14,2) NOT NULL,
  completed_quantity DECIMAL(14,2) NOT NULL DEFAULT 0,
  planned_date DATE NOT NULL,
  INDEX idx_work_orders_factory_date (factory, planned_date)
);
CREATE TABLE IF NOT EXISTS purchase_orders (
  purchase_order_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  po_number VARCHAR(40) NOT NULL UNIQUE,
  supplier_id BIGINT NOT NULL,
  planned_date DATE NOT NULL,
  delivered_date DATE,
  status VARCHAR(32) NOT NULL,
  CONSTRAINT fk_purchase_supplier FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id),
  INDEX idx_purchase_supplier_date (supplier_id, planned_date)
);
CREATE TABLE IF NOT EXISTS inventory_balances (
  inventory_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  material_id BIGINT NOT NULL,
  factory VARCHAR(80) NOT NULL,
  quantity DECIMAL(14,2) NOT NULL DEFAULT 0,
  snapshot_date DATE NOT NULL,
  CONSTRAINT fk_inventory_material FOREIGN KEY (material_id) REFERENCES materials(material_id),
  INDEX idx_inventory_factory_snapshot (factory, snapshot_date)
);
INSERT IGNORE INTO suppliers (supplier_code, supplier_name, region) VALUES
  ('SUP-001', '华东精密供应', '华东'), ('SUP-002', '西南新材', '西南');
INSERT IGNORE INTO materials (material_code, material_name, product_line, safety_stock) VALUES
  ('MAT-001', '控制器总成', '智能控制', 100),
  ('MAT-002', '动力模块', '新能源', 80),
  ('MAT-003', '传感器组件', '智能控制', 120);
INSERT IGNORE INTO production_work_orders
  (order_number, factory, product_line, planned_quantity, completed_quantity, planned_date)
VALUES
  ('WO-20260801', '成都工厂', '智能控制', 1000, 930, CURRENT_DATE - INTERVAL 5 DAY),
  ('WO-20260802', '苏州工厂', '新能源', 800, 760, CURRENT_DATE - INTERVAL 4 DAY),
       ('WO-20260803', '成都工厂', '新能源', 600, 510, CURRENT_DATE - INTERVAL 3 DAY);
INSERT IGNORE INTO production_work_orders (order_number, factory, product_line, planned_quantity, completed_quantity, planned_date) VALUES
  ('WO-20260804','苏州工厂','智能控制',1200,1140,CURRENT_DATE - INTERVAL 10 DAY),
  ('WO-20260805','成都工厂','新能源',900,720,CURRENT_DATE - INTERVAL 12 DAY),
  ('WO-20260806','上海工厂','智能控制',700,690,CURRENT_DATE - INTERVAL 18 DAY),
  ('WO-20260807','上海工厂','新能源',1500,1280,CURRENT_DATE - INTERVAL 22 DAY),
  ('WO-20260808','苏州工厂','新能源',1100,1030,CURRENT_DATE - INTERVAL 27 DAY);
INSERT IGNORE INTO purchase_orders (po_number, supplier_id, planned_date, delivered_date, status)
SELECT v.po_number, s.supplier_id, v.planned_date, v.delivered_date, v.status FROM
(SELECT 'PO-20260801' po_number,'SUP-001' supplier_code,CURRENT_DATE-INTERVAL 8 DAY planned_date,CURRENT_DATE-INTERVAL 7 DAY delivered_date,'delivered' status UNION ALL
 SELECT 'PO-20260802','SUP-002',CURRENT_DATE-INTERVAL 6 DAY,CURRENT_DATE-INTERVAL 2 DAY,'delivered' UNION ALL
 SELECT 'PO-20260803','SUP-001',CURRENT_DATE-INTERVAL 4 DAY,NULL,'late' UNION ALL
 SELECT 'PO-20260804','SUP-002',CURRENT_DATE-INTERVAL 2 DAY,NULL,'open' UNION ALL
 SELECT 'PO-20260805','SUP-001',CURRENT_DATE-INTERVAL 20 DAY,CURRENT_DATE-INTERVAL 19 DAY,'delivered' UNION ALL
 SELECT 'PO-20260806','SUP-002',CURRENT_DATE-INTERVAL 25 DAY,CURRENT_DATE-INTERVAL 23 DAY,'delivered') v
JOIN suppliers s ON s.supplier_code=v.supplier_code;
UPDATE purchase_orders SET delivered_date = DATE_SUB(planned_date, INTERVAL 1 DAY)
WHERE po_number IN ('PO-20260801', 'PO-20260802', 'PO-20260805');

CREATE TABLE IF NOT EXISTS quality_inspections (
  inspection_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  work_order_id BIGINT NOT NULL,
  inspected_quantity DECIMAL(14,2) NOT NULL,
  passed_quantity DECIMAL(14,2) NOT NULL,
  inspected_at DATE NOT NULL,
  CONSTRAINT fk_quality_work_order FOREIGN KEY (work_order_id) REFERENCES production_work_orders(work_order_id)
);
CREATE TABLE IF NOT EXISTS sales_orders (
  sales_order_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  order_number VARCHAR(40) NOT NULL UNIQUE,
  factory VARCHAR(80) NOT NULL,
  product_line VARCHAR(80) NOT NULL,
  ordered_quantity DECIMAL(14,2) NOT NULL,
  delivered_quantity DECIMAL(14,2) NOT NULL DEFAULT 0,
  promised_date DATE NOT NULL,
  delivered_date DATE
);
CREATE TABLE IF NOT EXISTS delivery_plans (
  delivery_plan_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  sales_order_id BIGINT NOT NULL,
  planned_date DATE NOT NULL,
  status VARCHAR(32) NOT NULL,
  CONSTRAINT fk_delivery_sales_order FOREIGN KEY (sales_order_id) REFERENCES sales_orders(sales_order_id)
);
INSERT IGNORE INTO quality_inspections (work_order_id, inspected_quantity, passed_quantity, inspected_at)
SELECT work_order_id, planned_quantity, completed_quantity - 12, planned_date FROM production_work_orders;
INSERT IGNORE INTO inventory_balances (material_id, factory, quantity, snapshot_date)
SELECT m.material_id, x.factory, x.quantity, CURRENT_DATE FROM materials m JOIN
(SELECT 'MAT-001' code,'苏州工厂' factory,180 quantity UNION ALL SELECT 'MAT-002','苏州工厂',42 UNION ALL SELECT 'MAT-003','上海工厂',210 UNION ALL SELECT 'MAT-001','上海工厂',55) x ON x.code=m.material_code;
INSERT IGNORE INTO sales_orders (order_number, factory, product_line, ordered_quantity, delivered_quantity, promised_date)
VALUES ('SO-20260801', '成都工厂', '智能控制', 500, 420, CURRENT_DATE + INTERVAL 3 DAY),
       ('SO-20260802', '苏州工厂', '新能源', 380, 380, CURRENT_DATE - INTERVAL 1 DAY),
       ('SO-20260803', '上海工厂', '新能源', 900, 760, CURRENT_DATE + INTERVAL 3 DAY),
       ('SO-20260804', '上海工厂', '智能控制', 620, 620, CURRENT_DATE - INTERVAL 5 DAY),
       ('SO-20260805', '成都工厂', '新能源', 700, 500, CURRENT_DATE + INTERVAL 5 DAY);
INSERT IGNORE INTO delivery_plans (sales_order_id, planned_date, status)
SELECT sales_order_id, promised_date, IF(delivered_quantity >= ordered_quantity, 'completed', 'at_risk') FROM sales_orders;
