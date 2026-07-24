# 其他入库单创建 (该接口将要下线，如有需要，请调V2接口：/api/warehouseInOut/inRecord/v2) 

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/warehouseInOut/inRecord.json:
    post:
      summary: '其他入库单创建 (该接口将要下线，如有需要，请调V2接口：/api/warehouseInOut/inRecord/v2) '
      deprecated: false
      description: ''
      operationId: inRecordUsingPOST
      tags:
        - 仓库/其他入库
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
              $ref: '#/components/schemas/WarehouseInOpenDto'
            example: ''
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: '#/components/schemas/OpenResult%C2%ABstring%C2%BB'
          headers: {}
          x-apifox-name: 成功
        '201':
          description: Created
          content:
            '*/*':
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: 成功
        '401':
          description: Unauthorized
          content:
            '*/*':
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: 没有权限
        '403':
          description: Forbidden
          content:
            '*/*':
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: 禁止访问
        '404':
          description: Not Found
          content:
            '*/*':
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: 记录不存在
      security: []
      x-apifox-folder: 仓库/其他入库
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-51516621-run
components:
  schemas:
    WarehouseInOpenDto:
      type: object
      required:
        - warehouseId
        - apportionType
        - items
        - status
        - type
      properties:
        warehouseId:
          type: string
          description: warehouseId, 仓库id
        remark:
          type: string
          description: 备注, 不能超过1000个字符
        shipFee:
          type: string
          description: 运费, 0 < 运费 < 999999
        otherFee:
          type: string
          description: 其它费用, 0 < 其他费用 < 99999
        apportionType:
          type: string
          description: 费用分配方式:0不分配,1按金额，2按数量
        items:
          type: array
          description: items, 入库商品合集
          items:
            $ref: '#/components/schemas/WarehouseInItemOpenDto'
        status:
          type: string
          description: 保存单据状态:-3:草稿 -2:待审核 -1:已驳回 0:未确认 1:保存并发布
        type:
          type: string
          description: 入库类型 0:其他入库,1:采购入库,2:维修入库,3:退货入库,4:还回入库,5:次品入库
      title: WarehouseInOpenDto
      x-apifox-orders:
        - warehouseId
        - remark
        - shipFee
        - otherFee
        - apportionType
        - items
        - status
        - type
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    WarehouseInItemOpenDto:
      type: object
      required:
        - commodityId
        - commoditySku
      properties:
        commodityId:
          type: string
          description: 商品id
        commoditySku:
          type: string
          description: 商品sku
        shopName:
          type: string
          description: 店铺名
        shopId:
          type: string
          description: 店铺id
        fnSku:
          type: string
          description: fnSku
        goods:
          type: string
          description: 可用数, 需为整数, 0 < 可用数 < 999999
        defective:
          type: string
          description: 次品数, 需为整数, 0 < 次品数 < 999999
        perPurchase:
          type: string
          description: 采购单价 0.0000 < 单价 < 999999
        mainImage:
          type: string
          description: 图片
        commodityName:
          type: string
          description: 品名
        perFee:
          type: string
          description: 单位费用
        perInventoryCost:
          type: string
          description: 单位成本
        totalPurchase:
          type: string
          description: 总货值
        totalFee:
          type: string
          description: 总费用
        inventoryCost:
          type: string
          description: 总货值
        isGroup:
          type: string
          description: 1表示组合sku 2表示加工SKU
        childSkus:
          type: array
          description: 子商品sku集合
          items:
            $ref: '#/components/schemas/ChildOpenSku'
        adjustStatus:
          type: string
          description: 成本补录单状态 0 未补录 1 已补录
        id:
          type: string
          description: 入库单明细id
        shelfNoAvailable:
          type: string
          description: 用户选择的良品货架位
        shelfNoDefective:
          type: string
          description: 用户选择的次品货架位
        shelfAvailableVo: &ref_0
          $ref: '#/components/schemas/RecordShelfInfoOpenDTO'
        shelfDefectiveVo: *ref_0
      title: WarehouseInItemOpenDto
      x-apifox-orders:
        - commodityId
        - commoditySku
        - shopName
        - shopId
        - fnSku
        - goods
        - defective
        - perPurchase
        - mainImage
        - commodityName
        - perFee
        - perInventoryCost
        - totalPurchase
        - totalFee
        - inventoryCost
        - isGroup
        - childSkus
        - adjustStatus
        - id
        - shelfNoAvailable
        - shelfNoDefective
        - shelfAvailableVo
        - shelfDefectiveVo
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    RecordShelfInfoOpenDTO:
      type: object
      properties:
        id:
          type: string
          description: 货架位库存id
        sid:
          type: string
          description: 货架位id
        'no':
          type: string
          description: 货架位编号
        type:
          type: string
          description: 货架位类型
        qty:
          type: string
          description: 在此货架位出入库数量
        sku:
          type: string
          description: sku
        fnsku:
          type: string
          description: fnsku
      title: RecordShelfInfoOpenDTO
      x-apifox-orders:
        - id
        - sid
        - 'no'
        - type
        - qty
        - sku
        - fnsku
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ChildOpenSku:
      type: object
      properties:
        sku:
          type: string
          description: sku
        num:
          type: string
          description: 数量
        id:
          type: string
          description: 商品id
        name:
          type: string
          description: 商品名称
        imgUrl:
          type: string
          description: 图片
        stockAvailable:
          type: string
          description: 可用数
      title: ChildOpenSku
      x-apifox-orders:
        - sku
        - num
        - id
        - name
        - imgUrl
        - stockAvailable
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«string»:
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
          type: string
          description: 数据
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«string»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
