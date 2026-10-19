# 演示源库数据字典

> 数据性质：合成演示数据 | 初始化脚本：`database/seeds/postgresql/001_supply_chain.sql` 与 `002_supply_chain_test_data.sql`

| 表 | 用途 | 关键字段 |
| --- | --- | --- |
| `suppliers` | 供应商主数据 | `supplier_code`, `region` |
| `materials` | 物料与安全库存 | `material_code`, `safety_stock` |
| `purchase_orders` | 采购交付 | `po_number`, `planned_date`, `delivered_date`, `status` |
| `production_work_orders` | 生产计划与完工 | `order_number`, `planned_quantity`, `completed_quantity` |
| `inventory_balances` | 工厂物料快照 | `material_id`, `factory`, `quantity`, `snapshot_date` |
| `quality_inspections` | 工单质量检验 | `work_order_id`, `inspected_quantity`, `passed_quantity` |
| `sales_orders` | 客户订单履约 | `order_number`, `ordered_quantity`, `delivered_quantity`, `promised_date` |
| `delivery_plans` | 交付里程碑 | `sales_order_id`, `planned_date`, `actual_date` |

测试数据脚本使用业务编码作为幂等键，可重复执行；不要将该库配置为平台数据库。
