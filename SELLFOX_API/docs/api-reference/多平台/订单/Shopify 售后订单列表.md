# Shopify 售后订单列表

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/multiplatform/after/sale/order/shopify/list.json:
    post:
      summary: Shopify 售后订单列表
      deprecated: false
      description: Shopify 售后订单列表
      operationId: shopifyListUsingPOST
      tags:
        - 多平台/订单
        - 多平台/售后单
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
              $ref: '#/components/schemas/ShopifyAfterSaleOrderSearchQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABPage%C2%ABShopifyAfterSaleOrderVo%C2%BB%C2%BB
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
      x-apifox-folder: 多平台/订单
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-510555319-run
components:
  schemas:
    ShopifyAfterSaleOrderSearchQo:
      type: object
      required:
        - pageNo
        - pageSize
      properties:
        afterSaleType:
          type: array
          description: 退货类型:0 退货，1 退款
          items:
            type: string
        pageNo:
          type: string
          description: 第几页
        pageSize:
          type: string
          description: 每页大小,<= 1000
        refundStatus:
          type: array
          description: 退款状态:0 部分退款，1 全额退款
          items:
            type: string
        returnStatus:
          type: array
          description: 退货状态
          items:
            type: string
        shopIdList:
          type: array
          description: 店铺ID,通过多平台店铺列表接口获取
          items:
            type: integer
            format: int32
        marketplaceCodeList:
          type: array
          description: 站点,US,CA,UK,DE 等, 国家2位CODE
          items:
            type: string
          examples:
            - US
        returnReason:
          type: array
          description: 退货原因
          items:
            type: string
        dateStart:
          type: string
          description: '开始时间 格式: yyyy-MM-dd HH:mm:ss'
        dateType:
          type: string
          description: 筛选的日期类型:- purchase:订购时间- refundTime:退款时间- returnTime:退货时间
        dateEnd:
          type: string
          description: '结束时间 格式: yyyy-MM-dd HH:mm:ss'
        searchType:
          type: string
          description: 搜索类型:orderId/productTitle/productId/MSKU/SKU/refundNote/skuName
        searchContent:
          type: string
          description: 搜索内容
      title: ShopifyAfterSaleOrderSearchQo
      x-apifox-orders:
        - afterSaleType
        - pageNo
        - pageSize
        - refundStatus
        - returnStatus
        - shopIdList
        - marketplaceCodeList
        - returnReason
        - dateStart
        - dateType
        - dateEnd
        - searchType
        - searchContent
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«Page«ShopifyAfterSaleOrderVo»»:
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
          $ref: '#/components/schemas/Page%C2%ABShopifyAfterSaleOrderVo%C2%BB'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«Page«ShopifyAfterSaleOrderVo»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    Page«ShopifyAfterSaleOrderVo»:
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
            $ref: '#/components/schemas/ShopifyAfterSaleOrderVo'
      title: Page«ShopifyAfterSaleOrderVo»
      x-apifox-orders:
        - pageNo
        - pageSize
        - totalPage
        - totalSize
        - rows
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ShopifyAfterSaleOrderVo:
      type: object
      properties:
        afterRefundAmount:
          type: number
        afterSaleType:
          type: array
          items:
            type: string
        currency:
          type: string
        marketplaceCode:
          type: string
        marketplaceName:
          type: string
        orderNo:
          type: string
        productInfo:
          type: array
          items:
            $ref: '#/components/schemas/ProductInfo'
        purchaseDate:
          type: string
        refundNote:
          type: array
          items:
            $ref: '#/components/schemas/RefundNote'
        refundStatus:
          type: string
        refundTime:
          type: string
        returnReason:
          type: array
          items:
            $ref: '#/components/schemas/ReturnReason'
        returnStatus:
          type: string
        returnTime:
          type: string
        shopId:
          type: integer
          format: int32
        shopName:
          type: string
        totalDiscountsAmount:
          type: number
        totalRefundAmount:
          type: number
        totalShippingPriceAmount:
          type: number
        totalTaxAmount:
          type: number
      title: ShopifyAfterSaleOrderVo
      x-apifox-orders:
        - afterRefundAmount
        - afterSaleType
        - currency
        - marketplaceCode
        - marketplaceName
        - orderNo
        - productInfo
        - purchaseDate
        - refundNote
        - refundStatus
        - refundTime
        - returnReason
        - returnStatus
        - returnTime
        - shopId
        - shopName
        - totalDiscountsAmount
        - totalRefundAmount
        - totalShippingPriceAmount
        - totalTaxAmount
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ReturnReason:
      type: object
      properties:
        msku:
          type: string
        productId:
          type: string
        returnNum:
          type: integer
          format: int32
        returnReason:
          type: string
        returnTime:
          type: string
      title: ReturnReason
      x-apifox-orders:
        - msku
        - productId
        - returnNum
        - returnReason
        - returnTime
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    RefundNote:
      type: object
      properties:
        refundAmount:
          type: number
        refundNote:
          type: string
        refundTime:
          type: string
      title: RefundNote
      x-apifox-orders:
        - refundAmount
        - refundNote
        - refundTime
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ProductInfo:
      type: object
      properties:
        carrier:
          type: string
        currentQty:
          type: integer
          format: int32
        description:
          type: string
        imageUrl:
          type: string
        isReturnNum:
          type: integer
          format: int32
        msku:
          type: string
        originalTotalPrice:
          type: number
        originalUnitPrice:
          type: number
        productId:
          type: string
        productName:
          type: string
        refundAmount:
          type: number
        returnNum:
          type: integer
          format: int32
        returnQty:
          type: integer
          format: int32
        returnReason:
          type: string
        returnWarehouseType:
          type: string
        salesNum:
          type: integer
          format: int32
        salesQty:
          type: integer
          format: int32
        shouldRefundNum:
          type: integer
          format: int32
        sku:
          type: string
        title:
          type: string
        trackingNumber:
          type: string
        unReturnNum:
          type: integer
          format: int32
        warehouseCountry:
          type: string
      title: ProductInfo
      x-apifox-orders:
        - carrier
        - currentQty
        - description
        - imageUrl
        - isReturnNum
        - msku
        - originalTotalPrice
        - originalUnitPrice
        - productId
        - productName
        - refundAmount
        - returnNum
        - returnQty
        - returnReason
        - returnWarehouseType
        - salesNum
        - salesQty
        - shouldRefundNum
        - sku
        - title
        - trackingNumber
        - unReturnNum
        - warehouseCountry
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
