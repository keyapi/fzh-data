# 查询FBA库存明细

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/inventoryManage/fba/pageList.json:
    post:
      summary: 查询FBA库存明细
      deprecated: false
      description: ''
      operationId: pageListApiUsingPOST
      tags:
        - 仓库/FBA库存
        - 仓库
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
              $ref: '#/components/schemas/FbaUserInventorySearchOpenParam'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABPage%C2%ABFbaInventoryManageListOpenVo%C2%BB%C2%BB
          headers: {}
          x-apifox-name: 成功
        '201':
          description: Created
          headers: {}
          x-apifox-name: 成功
        '401':
          description: Unauthorized
          headers: {}
          x-apifox-name: 没有权限
        '403':
          description: Forbidden
          headers: {}
          x-apifox-name: 禁止访问
        '404':
          description: Not Found
          headers: {}
          x-apifox-name: 记录不存在
      security: []
      x-order: '7'
      x-apifox-folder: 仓库/FBA库存
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-51516618-run
components:
  schemas:
    FbaUserInventorySearchOpenParam:
      type: object
      properties:
        pageNo:
          type: string
          description: 第几页
        pageSize:
          type: string
          description: 每页大小
        currency:
          type: string
          description: 币种
        hideZero:
          type: string
          description: 是否隐藏总库存为0的数据, 可选值true,false
        hideDeletedPrd:
          type: string
          description: 是否隐藏已删除产品, 可选值true,false
        needMergeShare:
          type: string
          description: 是否需要合并共享仓数据
        productDevIds:
          type: string
          description: productDevIds
        commodityDevIds:
          type: string
          description: commodityDevIds
        skus:
          type: array
          description: skus
          items:
            type: string
        asins:
          type: array
          description: asins
          items:
            type: string
        commodityIds:
          type: array
          description: commodityIds
          items:
            type: string
        productIds:
          type: array
          description: productIds
          items:
            type: string
        shopIdList:
          type: array
          description: shopIdList
          items:
            type: string
      title: FbaUserInventorySearchOpenParam
      x-apifox-orders:
        - pageNo
        - pageSize
        - currency
        - hideZero
        - hideDeletedPrd
        - needMergeShare
        - productDevIds
        - commodityDevIds
        - skus
        - asins
        - commodityIds
        - productIds
        - shopIdList
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«Page«FbaInventoryManageListOpenVo»»:
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
          $ref: '#/components/schemas/Page%C2%ABFbaInventoryManageListOpenVo%C2%BB'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«Page«FbaInventoryManageListOpenVo»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    Page«FbaInventoryManageListOpenVo»:
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
            $ref: '#/components/schemas/FbaInventoryManageListOpenVo'
      title: Page«FbaInventoryManageListOpenVo»
      x-apifox-orders:
        - pageNo
        - pageSize
        - totalPage
        - totalSize
        - rows
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FbaInventoryManageListOpenVo:
      type: object
      properties:
        id:
          type: string
          description: ID
        shopId:
          type: string
          description: 店铺ID
        marketplaceId:
          type: string
          description: 站点ID
        sellingPartnerId:
          type: string
          description: 亚马逊卖家编号
        shareKey:
          type: string
          description: 共享的键，用于查询时合并数据
        shareType:
          type: string
          description: 共享类型，0：不共享，1：共享
        shareShops:
          type: string
          description: 共享的国家对应的店铺ID
        panOffer:
          type: string
          description: 0：表示非PAN_EU/PAN_NA计划（EFN），1：PAN_EU/PAN_NA。
        fullCid:
          type: string
          description: 配对商品分类全路径id
        mainImage:
          type: string
          description: 主图
        asin:
          type: string
          description: ASIN
        sku:
          type: string
          description: 卖家SKU
        fnSku:
          type: string
          description: Fullfilment Network SKU
        condition:
          type: string
          description: 产品状况
        commodityId:
          type: string
          description: 配对商品id
        commodityName:
          type: string
          description: 商品中文名称
        commoditySku:
          type: string
          description: 商品sku
        avgInventoryCost:
          type: string
          description: 平均库存成本
        avgTransportCost:
          type: string
          description: 平均头程费用
        inventoryCosts:
          type: string
          description: 库存成本((配对商品采购成本+头程费用)*(可售+待调仓+调仓中+待发货+在途+入库中))
        purchaseCosts:
          type: string
          description: 货值((配对商品的采购成本)*(可售+待调仓+调仓中+待发货+在途+入库中))
        currency:
          type: string
          description: 成本,货值货币单位
        multiCountryData:
          type: array
          description: 多国库存数量明细
          items:
            $ref: '#/components/schemas/FbaInventoryCountryVo'
        available:
          type: string
          description: 可售
        reservedTransfer:
          type: string
          description: 预留转运
        reservedProcessing:
          type: string
          description: 预留处理中
        reservedCustomerorders:
          type: string
          description: 预留订单
        inboundWorking:
          type: string
          description: 入库处理中
        inboundShipped:
          type: string
          description: 入库已发货
        inboundReceiving:
          type: string
          description: 入库正在接收
        unfulfillable:
          type: string
          description: 不可售
        invAge0to90Days:
          type: string
          description: 3个月库龄
        ageDto:
          $ref: '#/components/schemas/FbaInventoryAgeOpenVo'
        invAge91To180Days:
          type: string
          description: 3-6个月库龄
        invAge181To270Days:
          type: string
          description: 6-9个月库龄
        invAge271To365Days:
          type: string
          description: 9-12个月库存
        invAge365PlusDays:
          type: string
          description: 12个月以上库龄
        invAge0to30Days:
          type: string
          description: 0-30天库龄
        invAge31to60Days:
          type: string
          description: 31-60天库龄
        invAge61to90Days:
          type: string
          description: 61-90天库龄
        invAge181To330Days:
          type: string
          description: 6-11个月库龄
        invAge331To365Days:
          type: string
          description: 11-12个月库龄
        totalInventory:
          type: string
          description: 总库存
        inTransit:
          type: string
          description: 在途库存
        lastShareTime:
          type: string
          description: 最后一次共享时间
        warehouseName:
          type: string
          description: 仓库名称
        snapshotDate:
          type: string
          description: 库存库龄更新时间
        research:
          type: string
          description: 调查中
        lowCostStore:
          type: string
          description: 是否是低价商城
        unsoldInventory:
          type: string
          description: 滞销库存
        estimatedExcessQuantity:
          type: string
          description: 预计冗余商品数量
        fbaMinimumInventoryLevel:
          type: string
          description: 最低库存水平
        historicalDaysOfSupply:
          type: string
          description: 历史供货天数
        fbaInventoryLevelHealthStatus:
          type: string
          description: 库存水平分类
        researchDto:
          $ref: >-
            #/components/schemas/FBA%E5%BA%93%E5%AD%98%E8%B0%83%E6%9F%A5%E4%B8%AD%E7%9A%84%E5%AF%B9%E8%B1%A1
        presale:
          type: string
          description: 库存预售
        presaleDto:
          $ref: '#/components/schemas/%E5%BA%93%E5%AD%98%E9%A2%84%E5%94%AE'
        unfulfillableDto:
          $ref: >-
            #/components/schemas/FBA%E5%BA%93%E5%AD%98%E4%B8%8D%E5%8F%AF%E5%94%AE%E5%AF%B9%E8%B1%A1
      title: FbaInventoryManageListOpenVo
      x-apifox-orders:
        - id
        - shopId
        - marketplaceId
        - sellingPartnerId
        - shareKey
        - shareType
        - shareShops
        - panOffer
        - fullCid
        - mainImage
        - asin
        - sku
        - fnSku
        - condition
        - commodityId
        - commodityName
        - commoditySku
        - avgInventoryCost
        - avgTransportCost
        - inventoryCosts
        - purchaseCosts
        - currency
        - multiCountryData
        - available
        - reservedTransfer
        - reservedProcessing
        - reservedCustomerorders
        - inboundWorking
        - inboundShipped
        - inboundReceiving
        - unfulfillable
        - invAge0to90Days
        - ageDto
        - invAge91To180Days
        - invAge181To270Days
        - invAge271To365Days
        - invAge365PlusDays
        - invAge0to30Days
        - invAge31to60Days
        - invAge61to90Days
        - invAge181To330Days
        - invAge331To365Days
        - totalInventory
        - inTransit
        - lastShareTime
        - warehouseName
        - snapshotDate
        - research
        - lowCostStore
        - unsoldInventory
        - estimatedExcessQuantity
        - fbaMinimumInventoryLevel
        - historicalDaysOfSupply
        - fbaInventoryLevelHealthStatus
        - researchDto
        - presale
        - presaleDto
        - unfulfillableDto
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FBA库存不可售对象:
      type: object
      properties:
        customerDamaged:
          type: string
          description: 买家导致残损
        warehouseDamaged:
          type: string
          description: 在库房出现残损
        distributorDamaged:
          type: string
          description: 因分销商导致的残损
        carrierDamaged:
          type: string
          description: 因承运人导致的残损
        defective:
          type: string
          description: 存在瑕疵
        expired:
          type: string
          description: 已过期
      title: FBA库存不可售对象
      x-apifox-orders:
        - customerDamaged
        - warehouseDamaged
        - distributorDamaged
        - carrierDamaged
        - defective
        - expired
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    库存预售:
      type: object
      properties:
        reservedFutureSupplyQuantity:
          type: string
          description: 预留未来供货
        futureSupplyBuyableQuantity:
          type: string
          description: 可购买未来供货
      title: 库存预售
      x-apifox-orders:
        - reservedFutureSupplyQuantity
        - futureSupplyBuyableQuantity
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FBA库存调查中的对象:
      type: object
      properties:
        researchingQuantityInShortTerm:
          type: string
          description: 调查中 > 1-10天
        researchingQuantityInMidTerm:
          type: string
          description: 调查中 > 11-20天
        researchingQuantityInLongTerm:
          type: string
          description: 调查中 > 21-30天
      title: FBA库存调查中的对象
      x-apifox-orders:
        - researchingQuantityInShortTerm
        - researchingQuantityInMidTerm
        - researchingQuantityInLongTerm
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FbaInventoryAgeOpenVo:
      type: object
      properties:
        invAge0To30Days:
          type: string
          description: 0-30天库龄数据
        invAge31To60Days:
          type: string
          description: 31-60天库龄数据
        invAge61To90Days:
          type: string
          description: 61-90天库龄数据
      title: FbaInventoryAgeOpenVo
      x-apifox-orders:
        - invAge0To30Days
        - invAge31To60Days
        - invAge61To90Days
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FbaInventoryCountryVo:
      type: object
      properties:
        country:
          type: string
        countryName:
          type: string
        quantity:
          type: integer
          format: int32
      title: FbaInventoryCountryVo
      x-apifox-orders:
        - country
        - countryName
        - quantity
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
