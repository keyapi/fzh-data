# 查询请款池-SKU

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/finance/skuReconciliation/pageList.json:
    post:
      summary: 查询请款池-SKU
      deprecated: false
      description: ''
      operationId: skuReconciliationPageListUsingPOST
      tags:
        - 财务/请付款
        - 请付款
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
              $ref: '#/components/schemas/SkuReconciliationOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABSkuReconciliationOpenPage%C2%BB
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
      x-apifox-folder: 财务/请付款
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-436026008-run
components:
  schemas:
    SkuReconciliationOpenQo:
      type: object
      required:
        - searchDateType
        - beginDate
        - endDate
      properties:
        supplierIds:
          type: string
          description: 供应商
        searchDateType:
          type: string
          description: '时间类型: orderDate：下单时间,realShip:发货时间，默认createDate 创建时间'
          enum:
            - orderDate
            - realShip
        beginDate:
          type: string
          description: 开始时间
          examples:
            - '2025-08-03'
        endDate:
          type: string
          description: 结束时间
          examples:
            - '2025-08-03'
        searchType:
          type: string
          description: '搜索字段: commoditySku -sku,commodityName -品名,spu'
          enum:
            - commoditySku
            - commodityName
            - spu
        searchMode:
          type: string
          description: 搜索类型 exact:精准查询 blur:模糊查询
        searchContent:
          type: string
          description: 搜索内容,多个用%±%拼接
        pageNo:
          type: string
          description: 第几页
        pageSize:
          type: string
          description: 每页条数
      title: SkuReconciliationOpenQo
      x-apifox-orders:
        - supplierIds
        - searchDateType
        - beginDate
        - endDate
        - searchType
        - searchMode
        - searchContent
        - pageNo
        - pageSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«SkuReconciliationOpenPage»:
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
          $ref: '#/components/schemas/SkuReconciliationOpenPage'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«SkuReconciliationOpenPage»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    SkuReconciliationOpenPage:
      type: object
      properties:
        rows:
          type: array
          items:
            $ref: '#/components/schemas/SkuReconciliationOpenVo'
        pageNum:
          type: string
          description: 当前页
        pageSize:
          type: string
          description: 每页条数
        totalPage:
          type: string
          description: 总页数
        totalSize:
          type: string
          description: 总条数
      title: SkuReconciliationOpenPage
      x-apifox-orders:
        - rows
        - pageNum
        - pageSize
        - totalPage
        - totalSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    SkuReconciliationOpenVo:
      type: object
      properties:
        commoditySku:
          type: string
          description: SKU
        commodityName:
          type: string
          description: 品名
        spu:
          type: string
          description: SPU
        attributes:
          type: string
          description: 变种属性
        supplierName:
          type: string
          description: 供应商
        category:
          type: string
          description: 分类
        purchaseNum:
          type: string
          description: 采购量
        arrivalNum:
          type: string
          description: 到货量
        waitArrivalNum:
          type: string
          description: 待到货量
        unCompleteNum:
          type: string
          description: 结束剩余到货量
        currency:
          type: string
          description: 币种
        stockGoodsNum:
          type: string
          description: 良品入库量
        stockDefectiveNum:
          type: string
          description: 次品入库量
        arrivalInNum:
          type: string
          description: 入库量
        returnedNum:
          type: string
          description: 退货量
        purchaseGoodsAmount:
          type: string
          description: 采购货款
        priceAndTax:
          type: string
          description: 价税合计
        taxAmount:
          type: string
          description: 税额
        stockGoodsAmount:
          type: string
          description: 良品入库货款
        stockDefectiveAmount:
          type: string
          description: 次品入库货款
        stockAmount:
          type: string
          description: 入库货款
        returnedAmount:
          type: string
          description: 退货货款
        shipCount:
          type: string
          description: 发货量
        shipCountAmount:
          type: string
          description: 发货货款
        nonRequisitionShipAmount:
          type: string
          description: 未请发货货款
        needPayAmount:
          type: string
          description: 应付货款
        requisitionGoodsAmount:
          type: string
          description: 申请货款
        unRequisitionGoodsAmount:
          type: string
          description: 未请货款
        realPayAmount:
          type: string
          description: 实付金额
        payDiscountAmount:
          type: string
          description: 付款折扣金额
        paidAmount:
          type: string
          description: 已付金额
        unPayAmount:
          type: string
          description: 未付金额
      title: SkuReconciliationOpenVo
      x-apifox-orders:
        - commoditySku
        - commodityName
        - spu
        - attributes
        - supplierName
        - category
        - purchaseNum
        - arrivalNum
        - waitArrivalNum
        - unCompleteNum
        - currency
        - stockGoodsNum
        - stockDefectiveNum
        - arrivalInNum
        - returnedNum
        - purchaseGoodsAmount
        - priceAndTax
        - taxAmount
        - stockGoodsAmount
        - stockDefectiveAmount
        - stockAmount
        - returnedAmount
        - shipCount
        - shipCountAmount
        - nonRequisitionShipAmount
        - needPayAmount
        - requisitionGoodsAmount
        - unRequisitionGoodsAmount
        - realPayAmount
        - payDiscountAmount
        - paidAmount
        - unPayAmount
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
