-- Synthetic test fixtures only. Run after 001_supply_chain.sql in the read-only source DB.
INSERT INTO suppliers (supplier_code, supplier_name, region) VALUES
 ('SUP-003','北方电子协作厂','华北'), ('SUP-004','华南结构件','华南')
ON CONFLICT (supplier_code) DO NOTHING;
INSERT INTO materials (material_code, material_name, product_line, safety_stock) VALUES
 ('MAT-004','工业网关','智能控制',60), ('MAT-005','电芯模组','新能源',200)
ON CONFLICT (material_code) DO NOTHING;
INSERT INTO production_work_orders (order_number,factory,product_line,planned_quantity,completed_quantity,planned_date) VALUES
 ('WO-20260809','上海工厂','智能控制',900,810,CURRENT_DATE-30),
 ('WO-20260810','成都工厂','新能源',1400,1360,CURRENT_DATE-35),
 ('WO-20260811','苏州工厂','智能控制',500,430,CURRENT_DATE-40),
 ('WO-20260812','上海工厂','新能源',1000,940,CURRENT_DATE-45)
ON CONFLICT (order_number) DO NOTHING;
INSERT INTO purchase_orders (po_number,supplier_id,planned_date,delivered_date,status)
SELECT v.po_number,s.supplier_id,v.planned_date,v.delivered_date,v.status
FROM (VALUES
 ('PO-20260807','SUP-003',CURRENT_DATE-30,CURRENT_DATE-31,'delivered'),
 ('PO-20260808','SUP-004',CURRENT_DATE-28,CURRENT_DATE-25,'delivered'),
 ('PO-20260809','SUP-003',CURRENT_DATE-15,NULL,'late'),
 ('PO-20260810','SUP-004',CURRENT_DATE-7,NULL,'open')) v(po_number,code,planned_date,delivered_date,status)
JOIN suppliers s ON s.supplier_code=v.code
ON CONFLICT (po_number) DO NOTHING;
INSERT INTO inventory_balances(material_id,factory,quantity,snapshot_date)
SELECT m.material_id,v.factory,v.quantity,CURRENT_DATE FROM materials m
JOIN (VALUES ('MAT-004','成都工厂',18::numeric),('MAT-005','苏州工厂',75::numeric),('MAT-004','上海工厂',95::numeric)) v(code,factory,quantity)
ON v.code=m.material_code
WHERE NOT EXISTS (SELECT 1 FROM inventory_balances i WHERE i.material_id=m.material_id AND i.factory=v.factory AND i.snapshot_date=CURRENT_DATE);
INSERT INTO quality_inspections(work_order_id,inspected_quantity,passed_quantity,inspected_at)
SELECT p.work_order_id,p.planned_quantity,GREATEST(p.completed_quantity-15,0),p.planned_date
FROM production_work_orders p
WHERE p.order_number LIKE 'WO-2026081%' AND NOT EXISTS (SELECT 1 FROM quality_inspections q WHERE q.work_order_id=p.work_order_id);
INSERT INTO sales_orders(order_number,factory,product_line,ordered_quantity,delivered_quantity,promised_date,delivered_date) VALUES
 ('SO-20260806','成都工厂','智能控制',800,500,CURRENT_DATE-10,NULL),
 ('SO-20260807','苏州工厂','新能源',1200,1180,CURRENT_DATE+2,NULL),
 ('SO-20260808','上海工厂','智能控制',450,450,CURRENT_DATE-15,CURRENT_DATE-16)
ON CONFLICT (order_number) DO NOTHING;
INSERT INTO delivery_plans(sales_order_id,planned_date,actual_date)
SELECT s.sales_order_id,s.promised_date,s.delivered_date FROM sales_orders s
WHERE NOT EXISTS (SELECT 1 FROM delivery_plans d WHERE d.sales_order_id=s.sales_order_id);
