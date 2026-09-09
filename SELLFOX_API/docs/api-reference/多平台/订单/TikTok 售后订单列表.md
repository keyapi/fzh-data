# TikTok 售后订单列表

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/multiplatform/after/sale/order/tiktok/list.json:
    post:
      summary: TikTok 售后订单列表
      deprecated: false
      description: TikTok 售后订单列表
      operationId: tiktokListUsingPOST
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
              $ref: '#/components/schemas/TikTokAfterSaleOrderSearchQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABPage%C2%ABTikTokAfterSaleOrderVo%C2%BB%C2%BB
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-510555321-run
components:
  schemas:
    TikTokAfterSaleOrderSearchQo:
      type: object
      required:
        - pageNo
        - pageSize
      properties:
        pageNo:
          type: string
          description: 第几页
        shipNodeTypes:
          type: array
          description: 发货方式:SellerFulfilled/WFSFulfilled/3PLFulfilled
          items:
            type: string
        afterSalesType:
          type: array
          description: 售后类型:REFUND/RETURN_AND_REFUND/REPLACEMENT
          items:
            type: string
        pageSize:
          type: string
          description: 每页大小,<= 1000
        afterSaleStatus:
          type: array
          description: |-
            售后状态:RETURN_OR_REFUND_REQUEST_PENDING
            REFUND_OR_RETURN_REQUEST_REJECT
            AWAITING_BUYER_SHIP
            BUYER_SHIPPED_ITEM
            REJECT_RECEIVE_PACKAGE
            RETURN_OR_REFUND_REQUEST_SUCCESS
            RETURN_OR_REFUND_REQUEST_CANCEL
            RETURN_OR_REFUND_REQUEST_COMPLETE
            AWAITING_BUYER_RESPONSE
            REPLACEMENT_REQUEST_PENDING
            REPLACEMENT_REQUEST_REJECT
            REPLACEMENT_REQUEST_REFUND_SUCCESS
            REPLACEMENT_REQUEST_CANCEL
            REPLACEMENT_REQUEST_COMPLETE
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
          description: |-
            退款原因:Item/Product doesn't match description
            Missing item/product or parts/accessories
            Defective item/Product is defective or doesn't work
            Wrong item/product was sent
            Damaged item/product or packaging
            Fabric, material or style not as expected
            Color or pattern not as expected
            Suspected Counterfeit
            Quality or style not as expected
            Product is expired/spoiled
            Product not frozen on arrival
            Product/Package wouldn't arrive on time
            Package wasn't received
            Late delivery (Item arrived too late)
            Missed estimated delivery date
            Wrong delivery information
            Package lost
            Package delivery failed
            Shipping box damaged, but item is Ok
            Other
            General adjustment
            No longer needed
            Item doesn't fit
            Does not suit me
            Item is too big/long
            Item is too small/short
            Multiple sizes ordered
            Ordered incorrect size
            Unauthorised purchase
          items:
            type: string
        dateStart:
          type: string
          description: '开始时间 格式: yyyy-MM-dd HH:mm:ss'
        dateType:
          type: string
          description: 筛选的日期类型:purchase:订购时间afterSalesDate:售后时间
        dateEnd:
          type: string
          description: '结束时间 格式: yyyy-MM-dd HH:mm:ss'
        searchType:
          type: string
          description: >-
            搜索类型:afterSalesOrderId/orderId/productTitle/productId/msku/sku/skuName
        searchContent:
          type: string
          description: 搜索内容
      title: TikTokAfterSaleOrderSearchQo
      x-apifox-orders:
        - pageNo
        - shipNodeTypes
        - afterSalesType
        - pageSize
        - afterSaleStatus
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
    OpenResult«Page«TikTokAfterSaleOrderVo»»:
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
          $ref: '#/components/schemas/Page%C2%ABTikTokAfterSaleOrderVo%C2%BB'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«Page«TikTokAfterSaleOrderVo»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    Page«TikTokAfterSaleOrderVo»:
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
            $ref: '#/components/schemas/TikTokAfterSaleOrderVo'
      title: Page«TikTokAfterSaleOrderVo»
      x-apifox-orders:
        - pageNo
        - pageSize
        - totalPage
        - totalSize
        - rows
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    TikTokAfterSaleOrderVo:
      type: object
      properties:
        afterSaleOrderNo:
          type: string
        afterSaleReason:
          type: string
        afterSaleStatus:
          type: string
        afterSaleTime:
          type: string
        afterSalesType:
          type: string
        carrier:
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
        shopId:
          type: integer
          format: int32
        shopName:
          type: string
        trackingNumber:
          type: string
        updateDateTime:
          type: string
      title: TikTokAfterSaleOrderVo
      x-apifox-orders:
        - afterSaleOrderNo
        - afterSaleReason
        - afterSaleStatus
        - afterSaleTime
        - afterSalesType
        - carrier
        - currency
        - marketplaceCode
        - marketplaceName
        - orderNo
        - productInfo
        - purchaseDate
        - shopId
        - shopName
        - trackingNumber
        - updateDateTime
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
