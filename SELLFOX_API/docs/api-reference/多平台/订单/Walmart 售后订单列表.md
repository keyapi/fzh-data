# Walmart 售后订单列表

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/multiplatform/after/sale/order/walmart/list.json:
    post:
      summary: Walmart 售后订单列表
      deprecated: false
      description: Walmart 售后订单列表
      operationId: walmartListUsingPOST
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
              $ref: '#/components/schemas/WalmartAfterSaleOrderSearchQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABPage%C2%ABWalmartAfterSaleOrderVo%C2%BB%C2%BB
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-510555322-run
components:
  schemas:
    WalmartAfterSaleOrderSearchQo:
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
        afterSaleType:
          type: array
          description: 售后类型:PREORDER/REPLACEMENT/REFUND
          items:
            type: string
        pageSize:
          type: string
          description: 每页大小,<= 1000
        afterSaleStatus:
          type: array
          description: 售后状态:INITIATED/DELIVERED/COMPLETED
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
            退货原因:0 晚到
            1 购买了另一种尺寸或颜色
            2 在其他地方购买
            3 颜色不符合预期
            4 被损坏
            5 有缺陷
            6 设备/部件无法工作
            7 不喜欢这种面料
            8 难以设置/不兼容
            9 重复商品
            10 错误商品
            11 商品缺失
            12 交付后丢失
            13 运输中丢失
            14 更低的价格
            15 与描述不符
            16 不需要了
            17 其他，缺货
            18 包装或物品箱已损坏
            19 退还给发件人
            20 运输箱损坏
            21 尝试取消和尺寸错误/不合身
          items:
            type: string
        dateStart:
          type: string
          description: '开始时间 格式: yyyy-MM-dd HH:mm:ss'
        dateType:
          type: string
          description: 筛选的日期类型:- purchase:订购时间- refundCutoffTime:退款截止时间- returnTime:退货时间
        dateEnd:
          type: string
          description: '结束时间 格式: yyyy-MM-dd HH:mm:ss'
        searchType:
          type: string
          description: >-
            搜索类型:returnOrderId/buyerOrderId/orderId/replacementBuyerOrderId/productTitle/productId/MSKU/SKU/skuName/returnRefundDescription
        searchContent:
          type: string
          description: 搜索内容
      title: WalmartAfterSaleOrderSearchQo
      x-apifox-orders:
        - pageNo
        - shipNodeTypes
        - afterSaleType
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
    OpenResult«Page«WalmartAfterSaleOrderVo»»:
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
          $ref: '#/components/schemas/Page%C2%ABWalmartAfterSaleOrderVo%C2%BB'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«Page«WalmartAfterSaleOrderVo»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    Page«WalmartAfterSaleOrderVo»:
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
            $ref: '#/components/schemas/WalmartAfterSaleOrderVo'
      title: Page«WalmartAfterSaleOrderVo»
      x-apifox-orders:
        - pageNo
        - pageSize
        - totalPage
        - totalSize
        - rows
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    WalmartAfterSaleOrderVo:
      type: object
      properties:
        afterSaleType:
          type: string
        buyerName:
          type: string
        currency:
          type: string
        currentDeliveryStatus:
          type: string
        currentRefundStatus:
          type: string
        customerEmailId:
          type: string
        customerOrderId:
          type: string
        marketplaceCode:
          type: string
        marketplaceName:
          type: string
        platformOrderId:
          type: string
        productInfo:
          type: array
          items:
            $ref: '#/components/schemas/ProductInfo'
        replacementCustomerOrderId:
          type: string
        returnByDate:
          type: string
        returnDescription:
          type: string
        returnOrderNo:
          type: string
        returnReason:
          type: string
        returnTime:
          type: string
        shopId:
          type: integer
          format: int32
        shopName:
          type: string
        status:
          type: string
        totalRefundAmount:
          type: number
      title: WalmartAfterSaleOrderVo
      x-apifox-orders:
        - afterSaleType
        - buyerName
        - currency
        - currentDeliveryStatus
        - currentRefundStatus
        - customerEmailId
        - customerOrderId
        - marketplaceCode
        - marketplaceName
        - platformOrderId
        - productInfo
        - replacementCustomerOrderId
        - returnByDate
        - returnDescription
        - returnOrderNo
        - returnReason
        - returnTime
        - shopId
        - shopName
        - status
        - totalRefundAmount
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
