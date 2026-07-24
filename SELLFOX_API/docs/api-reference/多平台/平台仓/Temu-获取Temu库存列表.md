# Temu-获取Temu库存列表

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /openapi/psi/temu/inventory/pageList.json:
    post:
      summary: Temu-获取Temu库存列表
      deprecated: false
      description: ''
      operationId: pageListUsingPOST_21
      tags:
        - 多平台/平台仓
        - Temu库存
      parameters:
        - name: access_token
          in: query
          description: 通过获取token接口获得的token，详见 [获取 Access Token](doc-1589130)
          required: true
          example: '{{access_token}}'
          schema:
            type: string
        - name: client_id
          in: query
          description: client_id, 获取方式详见 [申请API权限](1748360)
          required: true
          example: '{{client_id}}'
          schema:
            type: string
        - name: timestamp
          in: query
          description: 13位毫秒时间戳，与当前时间差异不超过正负15分钟，示例：1668153260508
          required: true
          example: '121212'
          schema:
            type: string
        - name: nonce
          in: query
          description: '随机整数值，保证每个请求唯一，示例：11251 '
          required: true
          example: '121212'
          schema:
            type: string
        - name: sign
          in: query
          description: 请求签名，详见  [生成sign（签名）](doc-1749562)
          required: true
          example: '121212121'
          schema:
            type: string
        - name: Content-Type
          in: header
          description: 固定再header位置加入Content-Type:application/json
          example: application/json
          schema:
            type: string
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/TemuInventoryPageOpenQO'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABPage%C2%ABTemuInventoryOpenVO%C2%BB%C2%BB
          headers: {}
          x-apifox-name: ''
        '201':
          description: Created
          headers: {}
          x-apifox-name: ''
        '401':
          description: Unauthorized
          headers: {}
          x-apifox-name: ''
        '403':
          description: Forbidden
          headers: {}
          x-apifox-name: ''
        '404':
          description: Not Found
          headers: {}
          x-apifox-name: ''
      security: []
      x-order: '2147483647'
      x-apifox-folder: 多平台/平台仓
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-450307763-run
components:
  schemas:
    TemuInventoryPageOpenQO:
      type: object
      required:
        - pageNo
        - pageSize
      properties:
        shopId:
          type: string
          description: 店铺ID
        pageNo:
          type: string
          description: 第几页
        pageSize:
          type: string
          description: 每页大小
      title: TemuInventoryPageOpenQO
      x-apifox-orders:
        - shopId
        - pageNo
        - pageSize
      x--orders:
        - shopId
        - pageNo
        - pageSize
      x--ignore-properties: []
      x-apifox-folder: ''
    OpenResult«Page«TemuInventoryOpenVO»»:
      type: object
      properties:
        requestId:
          type: string
        code:
          type: integer
          format: int32
          description: code(默认0代表成功)
        msg:
          type: string
          description: 错误信息
        data:
          $ref: '#/components/schemas/Page%C2%ABTemuInventoryOpenVO%C2%BB'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«Page«TemuInventoryOpenVO»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x--orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x--ignore-properties: []
      x-apifox-folder: ''
    Page«TemuInventoryOpenVO»:
      type: object
      properties:
        pageNo:
          type: integer
          format: int32
          description: 页码
        pageSize:
          type: integer
          format: int32
          description: 每页条数
        totalPage:
          type: integer
          format: int32
          description: 总页数
        totalSize:
          type: integer
          format: int32
          description: 总条数
        rows:
          type: array
          description: 当前页数据
          items:
            $ref: '#/components/schemas/TemuInventoryOpenVO'
      title: Page«TemuInventoryOpenVO»
      x-apifox-orders:
        - pageNo
        - pageSize
        - totalPage
        - totalSize
        - rows
      x--orders:
        - pageNo
        - pageSize
        - totalPage
        - totalSize
        - rows
      x--ignore-properties: []
      x-apifox-folder: ''
    TemuInventoryOpenVO:
      type: object
      properties:
        id:
          type: integer
          format: int64
          description: ID
        shopId:
          type: integer
          format: int64
          description: 店铺ID
        shopName:
          type: string
          description: 店铺名称
        productId:
          type: integer
          format: int64
          description: 货品ID
        category:
          type: string
          description: 类目
        productSkuId:
          type: integer
          format: int64
          description: MSKU
        skuExtCode:
          type: string
          description: msku货号
        commoditySku:
          type: string
          description: 商品sku
        commodityName:
          type: string
          description: 商品品名
        className:
          type: string
          description: 属性
        productSkcId:
          type: integer
          format: int64
          description: 货品skcID
        skcExtCode:
          type: string
          description: skc货号
        productName:
          type: string
          description: 货品标题
        productSkcPicture:
          type: string
          description: 货品sku图片
        lackQuantitySum:
          type: integer
          format: int32
          description: 缺货数量
        adviceQuantitySum:
          type: integer
          format: int32
          description: 建议备货量
        oneSaleSum:
          type: integer
          format: int32
          description: 1天销量
        sevenSaleSum:
          type: integer
          format: int32
          description: 7天销量
        thirtySaleSum:
          type: integer
          format: int32
          description: 30天销量
        totalSaleSum:
          type: integer
          format: int32
          description: 总销量
        inCartNumber7dSum:
          type: integer
          format: int32
          description: 近7天用户加购数量
        inCartNumberSum:
          type: integer
          format: int32
          description: 加购数量
        sevenDaysSaleReferenceSum:
          type: number
          description: 7日销量参考
        inventorySum:
          type: integer
          format: int32
          description: 仓内可用库存
        unavailableSum:
          type: integer
          format: int32
          description: 仓内暂不可用库存
        waitOnShelfSum:
          type: integer
          format: int32
          description: 待上架库存
        waitInStockSum:
          type: integer
          format: int32
          description: 待入库库存
        waitQcSum:
          type: integer
          format: int32
          description: 已上架待质检库存
        expectedOccupiedSum:
          type: integer
          format: int32
          description: 预计占用库存
        waitReceiveSum:
          type: integer
          format: int32
          description: 已发货库存
        waitDeliverySum:
          type: integer
          format: int32
          description: 待发货库存
        waitApproveSum:
          type: integer
          format: int32
          description: 待审核备货库存
        inventoryCostSum:
          type: number
          description: 可用量成本
        unavailableCostSum:
          type: number
          description: 暂内用量成本
        waitReceiveCostSum:
          type: number
          description: 待收货量成本
        waitApproveCostSum:
          type: number
          description: 待审核量成本
        waitDeliveryCostSum:
          type: number
          description: 待发货量成本
        waitOnShelfCostSum:
          type: number
          description: 待上架成本
        waitInStockCostSum:
          type: number
          description: 待入库库存成本
        waitQcCostSum:
          type: number
          description: 已上架待质检库存成本
        expectedOccupiedCostSum:
          type: number
          description: 预计占用库存成本
        localWarehouseAbleSum:
          type: integer
          format: int64
          description: 本地可用库存
        localWarehouseAbleCostSum:
          type: number
          description: 本地可用库存成本
        pictureAuditStatus:
          type: integer
          format: int32
          description: 图片审核状态 1-未完成；2-已完成
        onSalesDurationOffline:
          type: integer
          format: int32
          description: 加入站点时长（单位：天）
        expectNormalSupplyTime:
          type: string
          format: date-time
          description: 预计正常供货时间
        inventoryRegion:
          type: integer
          format: int32
          description: 备货区域 1-国内备货，2-海外备货，3-保税仓备货
        inBlackList:
          type: integer
          format: int32
          description: 是否在备货黑名单内 0-否，1-是
        hotTag:
          type: integer
          format: int32
          description: 是否热销款 0-否，1-是
        isEnoughStock:
          type: integer
          format: int32
          description: 是否备货充足 0-否，1-是
        hasHotSku:
          type: integer
          format: int32
          description: 是否存在爆旺款SKU 0-否，1-是
        isFirst:
          type: integer
          format: int32
          description: 是否首单 0-否，1-是
        purchaseStockType:
          type: integer
          format: int32
          description: 是否是 JIT 备货 0-普通，1-JIT备货
        settlementType:
          type: integer
          format: int32
          description: 是否VIM 0-非VIM，1-VMIM
        autoCloseJit:
          type: integer
          format: int32
          description: 是否会自动关闭JIT 0-否，1-是
        closeJitStatus:
          type: integer
          format: int32
          description: >-
            JIT 转备货状态
            0-未申请，1-待调价，2-待备货，3-备货完成，待关闭JIT，4-JIT已关闭，5-调价失败，流程结束，6-备货失败，流程结束，7-发起涨价，流程结束
        firstProductSkuId:
          type: integer
          format: int32
          description: 第一个产品MSKU
        itemCount:
          type: integer
          format: int32
          description: item明细数量
        skuVOList:
          type: array
          description: 明细sku信息
          items:
            $ref: '#/components/schemas/TemuInventorySkuOpenVO'
      title: TemuInventoryOpenVO
      x-apifox-orders:
        - id
        - shopId
        - shopName
        - productId
        - category
        - productSkuId
        - skuExtCode
        - commoditySku
        - commodityName
        - className
        - productSkcId
        - skcExtCode
        - productName
        - productSkcPicture
        - lackQuantitySum
        - adviceQuantitySum
        - oneSaleSum
        - sevenSaleSum
        - thirtySaleSum
        - totalSaleSum
        - inCartNumber7dSum
        - inCartNumberSum
        - sevenDaysSaleReferenceSum
        - inventorySum
        - unavailableSum
        - waitOnShelfSum
        - waitInStockSum
        - waitQcSum
        - expectedOccupiedSum
        - waitReceiveSum
        - waitDeliverySum
        - waitApproveSum
        - inventoryCostSum
        - unavailableCostSum
        - waitReceiveCostSum
        - waitApproveCostSum
        - waitDeliveryCostSum
        - waitOnShelfCostSum
        - waitInStockCostSum
        - waitQcCostSum
        - expectedOccupiedCostSum
        - localWarehouseAbleSum
        - localWarehouseAbleCostSum
        - pictureAuditStatus
        - onSalesDurationOffline
        - expectNormalSupplyTime
        - inventoryRegion
        - inBlackList
        - hotTag
        - isEnoughStock
        - hasHotSku
        - isFirst
        - purchaseStockType
        - settlementType
        - autoCloseJit
        - closeJitStatus
        - firstProductSkuId
        - itemCount
        - skuVOList
      x--orders:
        - id
        - shopId
        - shopName
        - productId
        - category
        - productSkuId
        - skuExtCode
        - commoditySku
        - commodityName
        - className
        - productSkcId
        - skcExtCode
        - productName
        - productSkcPicture
        - lackQuantitySum
        - adviceQuantitySum
        - oneSaleSum
        - sevenSaleSum
        - thirtySaleSum
        - totalSaleSum
        - inCartNumber7dSum
        - inCartNumberSum
        - sevenDaysSaleReferenceSum
        - inventorySum
        - unavailableSum
        - waitOnShelfSum
        - waitInStockSum
        - waitQcSum
        - expectedOccupiedSum
        - waitReceiveSum
        - waitDeliverySum
        - waitApproveSum
        - inventoryCostSum
        - unavailableCostSum
        - waitReceiveCostSum
        - waitApproveCostSum
        - waitDeliveryCostSum
        - waitOnShelfCostSum
        - waitInStockCostSum
        - waitQcCostSum
        - expectedOccupiedCostSum
        - localWarehouseAbleSum
        - localWarehouseAbleCostSum
        - pictureAuditStatus
        - onSalesDurationOffline
        - expectNormalSupplyTime
        - inventoryRegion
        - inBlackList
        - hotTag
        - isEnoughStock
        - hasHotSku
        - isFirst
        - purchaseStockType
        - settlementType
        - autoCloseJit
        - closeJitStatus
        - firstProductSkuId
        - itemCount
        - skuVOList
      x--ignore-properties: []
      x-apifox-folder: ''
    TemuInventorySkuOpenVO:
      type: object
      properties:
        id:
          type: integer
          format: int64
          description: ID
        shopId:
          type: integer
          format: int64
          description: 店铺ID
        productId:
          type: integer
          format: int64
          description: 货品ID
        productSkcPicture:
          type: string
          description: skc图片
        productSkcId:
          type: integer
          format: int64
          description: 货品skcID
        productSkuId:
          type: integer
          format: int64
          description: MSKU
        skuExtCode:
          type: string
          description: sku货号
        className:
          type: string
          description: 属性
        supplyPrice:
          type: number
          description: 申报价
        ableSaleDays:
          type: string
          description: 可售天数
        ableSaleDaysInventory:
          type: string
          description: 库存可售天数
        warehouseAbleSaleDays:
          type: string
          description: 仓内库存可售天数
        lackQuantity:
          type: integer
          format: int32
          description: 缺货数量
        adviceQuantity:
          type: integer
          format: int32
          description: 建议下单
        stockDays:
          type: integer
          format: int32
          description: 备货天数
        safeInventoryDays:
          type: integer
          format: int32
          description: 安全库存天数
        purchaseConfig:
          type: string
          description: 下单逻辑
        oneSale:
          type: integer
          format: int32
          description: 今日销量
        lastSevenDaysSale:
          type: integer
          format: int32
          description: 近7天销量
        lastThirtyDaysSale:
          type: integer
          format: int32
          description: 近30天销量
        totalSale:
          type: integer
          format: int32
          description: 总销量
        inCartNumber7d:
          type: integer
          format: int32
          description: 近7天用户加购数量
        inCartNumber:
          type: integer
          format: int32
          description: 加购数量
        sevenDaysSaleReference:
          type: number
          description: 7日销量参考
        sevenDaysReferenceSaleType:
          type: integer
          format: int32
          description: 7日销量参考类型
        warehouseGroupId:
          type: integer
          format: int64
          description: 备货仓组ID
        warehouseGroupName:
          type: string
          description: 备货仓组
        priceReviewStatus:
          type: integer
          format: int32
          description: 核价状态 0:待核价;1:待供应商确认;2:核价通过;3:核价驳回;4:废弃;5:价格同步中
        waitOnShelfNum:
          type: integer
          format: int32
          description: 待上架库存
        salesInventoryNum:
          type: integer
          format: int32
          description: 仓内库存
        waitApproveInventoryNum:
          type: integer
          format: int32
          description: 待审核备货库存
        waitReceiveNum:
          type: integer
          format: int32
          description: 待收货库存
        waitDeliveryInventoryNum:
          type: integer
          format: int32
          description: 待发货库存
        warehouseInventoryNum:
          type: integer
          format: int32
          description: 仓内可用库存
        unavailableWarehouseInventoryNum:
          type: integer
          format: int32
          description: 仓内暂不可用库存
        expectedOccupiedInventoryNum:
          type: integer
          format: int32
          description: 预计占用库存
        waitInStock:
          type: integer
          format: int32
          description: 待入库库存
        waitQcNum:
          type: integer
          format: int32
          description: 已上架待质检库存
        localWarehouseAbleSum:
          type: integer
          format: int64
          description: 本地可用库存
        localWarehouseAbleCostSum:
          type: number
          description: 本地可用库存成本
        inventoryCost:
          type: number
          description: 可用量成本
        unavailableCost:
          type: number
          description: 暂不可用量成本
        waitReceiveCost:
          type: number
          description: 待收货量成本
        waitDeliveryCost:
          type: number
          description: 待发货量成本
        waitApproveCost:
          type: number
          description: 待审核量成本
        expectedOccupiedCost:
          type: number
          description: 预计占用库存成本
        waitInStockCost:
          type: number
          description: 待入库成本
        waitOnShelfCost:
          type: number
          description: 待上架库存成本
        waitQcCost:
          type: number
          description: 已上架待质检成本
        purchaseCost:
          type: number
          description: 采购成本
        supplierPrice:
          type: number
          description: 申报价
        commodityName:
          type: string
          description: 品名
        commoditySku:
          type: string
          description: SKU
      title: TemuInventorySkuOpenVO
      x-apifox-orders:
        - id
        - shopId
        - productId
        - productSkcPicture
        - productSkcId
        - productSkuId
        - skuExtCode
        - className
        - supplyPrice
        - ableSaleDays
        - ableSaleDaysInventory
        - warehouseAbleSaleDays
        - lackQuantity
        - adviceQuantity
        - stockDays
        - safeInventoryDays
        - purchaseConfig
        - oneSale
        - lastSevenDaysSale
        - lastThirtyDaysSale
        - totalSale
        - inCartNumber7d
        - inCartNumber
        - sevenDaysSaleReference
        - sevenDaysReferenceSaleType
        - warehouseGroupId
        - warehouseGroupName
        - priceReviewStatus
        - waitOnShelfNum
        - salesInventoryNum
        - waitApproveInventoryNum
        - waitReceiveNum
        - waitDeliveryInventoryNum
        - warehouseInventoryNum
        - unavailableWarehouseInventoryNum
        - expectedOccupiedInventoryNum
        - waitInStock
        - waitQcNum
        - localWarehouseAbleSum
        - localWarehouseAbleCostSum
        - inventoryCost
        - unavailableCost
        - waitReceiveCost
        - waitDeliveryCost
        - waitApproveCost
        - expectedOccupiedCost
        - waitInStockCost
        - waitOnShelfCost
        - waitQcCost
        - purchaseCost
        - supplierPrice
        - commodityName
        - commoditySku
      x--orders:
        - id
        - shopId
        - productId
        - productSkcPicture
        - productSkcId
        - productSkuId
        - skuExtCode
        - className
        - supplyPrice
        - ableSaleDays
        - ableSaleDaysInventory
        - warehouseAbleSaleDays
        - lackQuantity
        - adviceQuantity
        - stockDays
        - safeInventoryDays
        - purchaseConfig
        - oneSale
        - lastSevenDaysSale
        - lastThirtyDaysSale
        - totalSale
        - inCartNumber7d
        - inCartNumber
        - sevenDaysSaleReference
        - sevenDaysReferenceSaleType
        - warehouseGroupId
        - warehouseGroupName
        - priceReviewStatus
        - waitOnShelfNum
        - salesInventoryNum
        - waitApproveInventoryNum
        - waitReceiveNum
        - waitDeliveryInventoryNum
        - warehouseInventoryNum
        - unavailableWarehouseInventoryNum
        - expectedOccupiedInventoryNum
        - waitInStock
        - waitQcNum
        - localWarehouseAbleSum
        - localWarehouseAbleCostSum
        - inventoryCost
        - unavailableCost
        - waitReceiveCost
        - waitDeliveryCost
        - waitApproveCost
        - expectedOccupiedCost
        - waitInStockCost
        - waitOnShelfCost
        - waitQcCost
        - purchaseCost
        - supplierPrice
        - commodityName
        - commoditySku
      x--ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
