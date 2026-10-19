-- SupplyMind teaching source database. Run against a dedicated source database,
-- never against the platform PostgreSQL database.
CREATE TABLE IF NOT EXISTS suppliers (
  supplier_id BIGSERIAL PRIMARY KEY,
  supplier_code VARCHAR(40) UNIQUE NOT NULL,
  supplier_name VARCHAR(160) NOT NULL,
  region VARCHAR(80) NOT NULL
);
CREATE TABLE IF NOT EXISTS materials (
  material_id BIGSERIAL PRIMARY KEY,
  material_code VARCHAR(40) UNIQUE NOT NULL,
  material_name VARCHAR(160) NOT NULL,
  product_line VARCHAR(80) NOT NULL,
  safety_stock NUMERIC(14,2) NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS purchase_orders (
  purchase_order_id BIGSERIAL PRIMARY KEY,
  po_number VARCHAR(40) UNIQUE NOT NULL,
  supplier_id BIGINT NOT NULL REFERENCES suppliers(supplier_id),
  planned_date DATE NOT NULL,
  delivered_date DATE,
  status VARCHAR(32) NOT NULL
);
CREATE TABLE IF NOT EXISTS production_work_orders (
  work_order_id BIGSERIAL PRIMARY KEY,
  order_number VARCHAR(40) UNIQUE NOT NULL,
  factory VARCHAR(80) NOT NULL,
  product_line VARCHAR(80) NOT NULL,
  planned_quantity NUMERIC(14,2) NOT NULL,
  completed_quantity NUMERIC(14,2) NOT NULL DEFAULT 0,
  planned_date DATE NOT NULL
);
CREATE TABLE IF NOT EXISTS inventory_balances (
  inventory_id BIGSERIAL PRIMARY KEY,
  material_id BIGINT NOT NULL REFERENCES materials(material_id),
  factory VARCHAR(80) NOT NULL,
  quantity NUMERIC(14,2) NOT NULL DEFAULT 0,
  snapshot_date DATE NOT NULL
);
CREATE TABLE IF NOT EXISTS quality_inspections (
  inspection_id BIGSERIAL PRIMARY KEY,
  work_order_id BIGINT NOT NULL REFERENCES production_work_orders(work_order_id),
  inspected_quantity NUMERIC(14,2) NOT NULL,
  passed_quantity NUMERIC(14,2) NOT NULL,
  inspected_at DATE NOT NULL
);
CREATE TABLE IF NOT EXISTS sales_orders (
  sales_order_id BIGSERIAL PRIMARY KEY,
  order_number VARCHAR(40) UNIQUE NOT NULL,
  factory VARCHAR(80) NOT NULL,
  product_line VARCHAR(80) NOT NULL,
  ordered_quantity NUMERIC(14,2) NOT NULL,
  delivered_quantity NUMERIC(14,2) NOT NULL DEFAULT 0,
  promised_date DATE NOT NULL,
  delivered_date DATE
);
CREATE TABLE IF NOT EXISTS delivery_plans (
  delivery_plan_id BIGSERIAL PRIMARY KEY,
  sales_order_id BIGINT NOT NULL REFERENCES sales_orders(sales_order_id),
  planned_date DATE NOT NULL,
  actual_date DATE
);

INSERT INTO suppliers (supplier_code, supplier_name, region) VALUES
  ('SUP-001', '华东精密供应', '华东'),
  ('SUP-002', '西南新材', '西南')
ON CONFLICT (supplier_code) DO NOTHING;
INSERT INTO materials (material_code, material_name, product_line, safety_stock) VALUES
  ('MAT-001', '控制器总成', '智能控制', 100),
  ('MAT-002', '动力模块', '新能源', 80),
  ('MAT-003', '传感器组件', '智能控制', 120)
ON CONFLICT (material_code) DO NOTHING;

INSERT INTO production_work_orders
  (order_number, factory, product_line, planned_quantity, completed_quantity, planned_date)
VALUES
  ('WO-20260801', '成都工厂', '智能控制', 1000, 930, CURRENT_DATE - 5),
  ('WO-20260802', '苏州工厂', '新能源', 800, 760, CURRENT_DATE - 4),
  ('WO-20260803', '成都工厂', '新能源', 600, 510, CURRENT_DATE - 3)
ON CONFLICT (order_number) DO NOTHING;
INSERT INTO production_work_orders
  (order_number, factory, product_line, planned_quantity, completed_quantity, planned_date)
VALUES
  ('WO-20260804', '苏州工厂', '智能控制', 1200, 1140, CURRENT_DATE - 10),
  ('WO-20260805', '成都工厂', '新能源', 900, 720, CURRENT_DATE - 12),
  ('WO-20260806', '上海工厂', '智能控制', 700, 690, CURRENT_DATE - 18),
  ('WO-20260807', '上海工厂', '新能源', 1500, 1280, CURRENT_DATE - 22),
  ('WO-20260808', '苏州工厂', '新能源', 1100, 1030, CURRENT_DATE - 27)
ON CONFLICT (order_number) DO NOTHING;
INSERT INTO purchase_orders (po_number, supplier_id, planned_date, delivered_date, status)
SELECT v.po_number, s.supplier_id, v.planned_date, v.delivered_date, v.status
FROM (VALUES
  ('PO-20260801','SUP-001',CURRENT_DATE - 8,CURRENT_DATE - 7,'delivered'),
  ('PO-20260802','SUP-002',CURRENT_DATE - 6,CURRENT_DATE - 2,'delivered'),
  ('PO-20260803','SUP-001',CURRENT_DATE - 4,NULL,'late'),
  ('PO-20260804','SUP-002',CURRENT_DATE - 2,NULL,'open'),
  ('PO-20260805','SUP-001',CURRENT_DATE - 20,CURRENT_DATE - 19,'delivered'),
  ('PO-20260806','SUP-002',CURRENT_DATE - 25,CURRENT_DATE - 23,'delivered')
) v(po_number, supplier_code, planned_date, delivered_date, status)
JOIN suppliers s ON s.supplier_code = v.supplier_code
ON CONFLICT (po_number) DO NOTHING;
UPDATE purchase_orders SET delivered_date = planned_date - INTERVAL '1 day'
WHERE po_number IN ('PO-20260801', 'PO-20260802', 'PO-20260805');
INSERT INTO inventory_balances (material_id, factory, quantity, snapshot_date)
SELECT m.material_id, '成都工厂', v.quantity, CURRENT_DATE
FROM materials m
JOIN (VALUES ('MAT-001', 36::numeric), ('MAT-002', 160::numeric), ('MAT-003', 95::numeric)) v(code, quantity)
  ON v.code = m.material_code
WHERE NOT EXISTS (
  SELECT 1 FROM inventory_balances i
  WHERE i.material_id = m.material_id AND i.factory = '成都工厂' AND i.snapshot_date = CURRENT_DATE
);
INSERT INTO inventory_balances (material_id, factory, quantity, snapshot_date)
SELECT m.material_id, x.factory, x.quantity, CURRENT_DATE
FROM materials m
JOIN (VALUES ('MAT-001','苏州工厂',180::numeric),('MAT-002','苏州工厂',42::numeric),('MAT-003','上海工厂',210::numeric),('MAT-001','上海工厂',55::numeric)) x(code, factory, quantity)
  ON x.code = m.material_code
WHERE NOT EXISTS (SELECT 1 FROM inventory_balances i WHERE i.material_id=m.material_id AND i.factory=x.factory AND i.snapshot_date=CURRENT_DATE);
INSERT INTO quality_inspections (work_order_id, inspected_quantity, passed_quantity, inspected_at)
SELECT work_order_id, planned_quantity, GREATEST(completed_quantity - 8, 0), planned_date
FROM production_work_orders p
WHERE NOT EXISTS (SELECT 1 FROM quality_inspections q WHERE q.work_order_id=p.work_order_id);
INSERT INTO sales_orders (order_number, factory, product_line, ordered_quantity, delivered_quantity, promised_date, delivered_date)
VALUES
  ('SO-20260801','成都工厂','智能控制',500,420,CURRENT_DATE - 2,NULL),
  ('SO-20260802','苏州工厂','新能源',380,380,CURRENT_DATE - 1,CURRENT_DATE - 2),
  ('SO-20260803','上海工厂','新能源',900,760,CURRENT_DATE + 3,NULL),
  ('SO-20260804','上海工厂','智能控制',620,620,CURRENT_DATE - 5,CURRENT_DATE - 6),
  ('SO-20260805','成都工厂','新能源',700,500,CURRENT_DATE + 5,NULL)
ON CONFLICT (order_number) DO NOTHING;
INSERT INTO delivery_plans (sales_order_id, planned_date, actual_date)
SELECT sales_order_id, promised_date, delivered_date FROM sales_orders s
WHERE NOT EXISTS (SELECT 1 FROM delivery_plans d WHERE d.sales_order_id=s.sales_order_id);

CREATE INDEX IF NOT EXISTS idx_work_orders_factory_date ON production_work_orders(factory, planned_date);
CREATE INDEX IF NOT EXISTS idx_inventory_factory_snapshot ON inventory_balances(factory, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_purchase_orders_supplier_date ON purchase_orders(supplier_id, planned_date);

-- Run separately as a privileged administrator and replace the password through
-- a secret manager. The application must use this account, never the owner.
-- CREATE ROLE supplymind_readonly LOGIN PASSWORD '<inject-at-deploy-time>';
-- GRANT CONNECT ON DATABASE supplymind_demo TO supplymind_readonly;
-- GRANT USAGE ON SCHEMA public TO supplymind_readonly;
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO supplymind_readonly;
-- ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO supplymind_readonly;
