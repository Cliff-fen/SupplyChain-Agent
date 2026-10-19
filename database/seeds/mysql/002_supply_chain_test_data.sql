-- Synthetic test fixtures only. Run after 001_supply_chain.sql in the read-only source DB.
INSERT IGNORE INTO suppliers (supplier_code,supplier_name,region) VALUES ('SUP-003','北方电子协作厂','华北'),('SUP-004','华南结构件','华南');
INSERT IGNORE INTO materials (material_code,material_name,product_line,safety_stock) VALUES ('MAT-004','工业网关','智能控制',60),('MAT-005','电芯模组','新能源',200);
INSERT IGNORE INTO production_work_orders (order_number,factory,product_line,planned_quantity,completed_quantity,planned_date) VALUES
 ('WO-20260809','上海工厂','智能控制',900,810,CURRENT_DATE-INTERVAL 30 DAY),('WO-20260810','成都工厂','新能源',1400,1360,CURRENT_DATE-INTERVAL 35 DAY),('WO-20260811','苏州工厂','智能控制',500,430,CURRENT_DATE-INTERVAL 40 DAY),('WO-20260812','上海工厂','新能源',1000,940,CURRENT_DATE-INTERVAL 45 DAY);
INSERT IGNORE INTO purchase_orders (po_number,supplier_id,planned_date,delivered_date,status)
SELECT v.po_number,s.supplier_id,v.planned_date,v.delivered_date,v.status FROM
(SELECT 'PO-20260807' po_number,'SUP-003' code,CURRENT_DATE-INTERVAL 30 DAY planned_date,CURRENT_DATE-INTERVAL 31 DAY delivered_date,'delivered' status UNION ALL
 SELECT 'PO-20260808','SUP-004',CURRENT_DATE-INTERVAL 28 DAY,CURRENT_DATE-INTERVAL 25 DAY,'delivered' UNION ALL
 SELECT 'PO-20260809','SUP-003',CURRENT_DATE-INTERVAL 15 DAY,NULL,'late' UNION ALL SELECT 'PO-20260810','SUP-004',CURRENT_DATE-INTERVAL 7 DAY,NULL,'open') v JOIN suppliers s ON s.supplier_code=v.code;
INSERT IGNORE INTO inventory_balances(material_id,factory,quantity,snapshot_date) SELECT m.material_id,v.factory,v.quantity,CURRENT_DATE FROM materials m JOIN
(SELECT 'MAT-004' code,'成都工厂' factory,18 quantity UNION ALL SELECT 'MAT-005','苏州工厂',75 UNION ALL SELECT 'MAT-004','上海工厂',95) v ON v.code=m.material_code;
INSERT IGNORE INTO quality_inspections(work_order_id,inspected_quantity,passed_quantity,inspected_at) SELECT work_order_id,planned_quantity,GREATEST(completed_quantity-15,0),planned_date FROM production_work_orders WHERE order_number LIKE 'WO-2026081%';
INSERT IGNORE INTO sales_orders(order_number,factory,product_line,ordered_quantity,delivered_quantity,promised_date,delivered_date) VALUES
 ('SO-20260806','成都工厂','智能控制',800,500,CURRENT_DATE-INTERVAL 10 DAY,NULL),('SO-20260807','苏州工厂','新能源',1200,1180,CURRENT_DATE+INTERVAL 2 DAY,NULL),('SO-20260808','上海工厂','智能控制',450,450,CURRENT_DATE-INTERVAL 15 DAY,CURRENT_DATE-INTERVAL 16 DAY);
INSERT IGNORE INTO delivery_plans(sales_order_id,planned_date,status) SELECT sales_order_id,promised_date,IF(delivered_quantity>=ordered_quantity,'completed','at_risk') FROM sales_orders;
