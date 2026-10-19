# UCI Steel Plates Faults 公开制造数据来源说明

- 发布机构：University of California, Irvine Machine Learning Repository
- 数据集：[Steel Plates Faults](https://archive.ics.uci.edu/dataset/198/steel+plates+faults)
- 官方归档：[steel+plates+faults.zip](https://archive.ics.uci.edu/static/public/198/steel%2Bplates%2Bfaults.zip)
- 下载归档 SHA-256：`cb8eb9859198b63f053e443513036b401746fa517ef58bd17c846c6741c93919`
- 数据规模：1,941 条钢板缺陷检测记录，27 个测量变量和 7 类缺陷标签。

这是公开发布的真实钢板制造缺陷数据，但企业名称和工厂身份未公开。导入脚本会校验归档哈希，并按源行号幂等写入 `steel_plate_defects`。

```powershell
docker compose exec -T api python -m scripts.import_uci_steel
```
