# Temu-获取Temu货件列表

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /openapi/psi/temu/shipment/pageList.json:
    post:
      summary: Temu-获取Temu货件列表
      deprecated: false
      description: ''
      operationId: pageListUsingPOST_22
      tags:
        - 多平台/平台仓
        - Temu货件
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
              $ref: '#/components/schemas/TemuShipmentPageOpenQO'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABPage%C2%ABTemuShipmentOpenVO%C2%BB%C2%BB
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-450307764-run
components:
  schemas:
    TemuShipmentPageOpenQO:
      type: object
      required:
        - pageNo
        - pageSize
      properties:
        shipmentSnList:
          type: array
          items:
            type: string
        shopId:
          type: string
          description: 店铺ID
        createTimeStart:
          type: string
          description: 创建时间开始于，yyyy-MM-dd
          examples:
            - '2026-01-01'
        createTimeEnd:
          type: string
          description: 创建时间结束于，yyyy-MM-dd
          examples:
            - '2026-01-01'
        pageNo:
          type: string
          description: 第几页
        pageSize:
          type: string
          description: 每页大小
      title: TemuShipmentPageOpenQO
      x-apifox-orders:
        - shipmentSnList
        - shopId
        - createTimeStart
        - createTimeEnd
        - pageNo
        - pageSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«Page«TemuShipmentOpenVO»»:
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
          $ref: '#/components/schemas/Page%C2%ABTemuShipmentOpenVO%C2%BB'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«Page«TemuShipmentOpenVO»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    Page«TemuShipmentOpenVO»:
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
            $ref: '#/components/schemas/TemuShipmentOpenVO'
      title: Page«TemuShipmentOpenVO»
      x-apifox-orders:
        - pageNo
        - pageSize
        - totalPage
        - totalSize
        - rows
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    TemuShipmentOpenVO:
      type: object
      properties:
        id:
          type: integer
          format: int64
          description: 货件ID
        shipmentOrderSn:
          type: string
          description: 货件单号
        pickingListOrderSn:
          type: string
          description: 备货单号
        productPicture:
          type: string
          description: 商品图片
        productName:
          type: string
          description: 商品名称
        productSkcId:
          type: integer
          format: int64
          description: SKC
        skcExtCode:
          type: string
          description: SKC货号
        firstOrder:
          type: boolean
          description: 是否首单
        vmiOrder:
          type: boolean
          description: 是否VMI订单
        jitOrder:
          type: boolean
          description: 是否JIT备货
        urgencyOrder:
          type: boolean
          description: 是否紧急
        latestDeliverTime:
          type: string
          description: 最晚发货时间
        deliverLimitStatus:
          type: string
          description: 发货限制状态
        latestArrivalTime:
          type: string
          description: 最晚到货时间
        arrivalLimitStatus:
          type: string
          description: 到货限制状态 NORMAL、ABOUT_TO_OVERTIME、ALREADY_OVERTIME、SUCCESS
        shopId:
          type: integer
          format: int64
          description: 店铺ID
        shopName:
          type: string
          description: 店铺名称
        deliverMethod:
          type: integer
          format: int32
          description: 发货方式 0-无；1-自送；2-公司指定物流；3-第三方物流
        deliverMethodDesc:
          type: string
          description: 发货方式描述
        expressNo:
          type: string
          description: 物流单号
        expressCompanyName:
          type: string
          description: 物流公司名称
        pickupTime:
          type: string
          description: 预约取件时间
        driverName:
          type: string
          description: 司机姓名
        carNumber:
          type: string
          description: 车牌号
        driverPhone:
          type: string
          description: 司机联系方式
        deliverNumber:
          type: integer
          format: int32
          description: 发货数量
        deliverWarehouse:
          type: string
          description: 发货仓库
        receiveWarehouseName:
          type: string
          description: 收货仓库
        deliverBatchSn:
          type: string
          description: 发货批次
        packageTotalNum:
          type: integer
          format: int32
          description: 包裹总数
        deliverPackageNum:
          type: integer
          format: int32
          description: 已发货包裹数
        receivePackageNum:
          type: integer
          format: int32
          description: 已收货包裹数
        deliverTime:
          type: string
          description: 发货时间
        receiveTime:
          type: string
          description: 收货时间
        inboundTime:
          type: string
          description: 入库时间
        remark:
          type: string
          description: 备注
        shipmentStatus:
          type: string
          description: 货件状态
        shipmentStatusDesc:
          type: string
          description: 货件状态描述
        isPrintBoxMark:
          type: boolean
          description: 是否打印箱唛 false-未打印；true-已打印
        ifCanOperateDeliver:
          type: boolean
          description: 是否可发货 false-不可操作；true-可操作发货
        exitsLackOrSoldNum:
          type: integer
          format: int32
          description: 缺货售罄数量
        deliverOrderSnList:
          type: array
          description: 多平台发货单号列表
          items:
            type: string
        deliverInfo:
          $ref: >-
            #/components/schemas/%E5%8F%91%E8%B4%A7%E5%9C%B0%E5%9D%80%E4%BF%A1%E6%81%AF
        receiverInfo:
          $ref: >-
            #/components/schemas/%E6%94%B6%E8%B4%A7%E5%9C%B0%E5%9D%80%E4%BF%A1%E6%81%AF
        packageInfoList:
          type: array
          description: 包裹信息列表
          items:
            $ref: '#/components/schemas/%E5%8C%85%E8%A3%B9%E4%BF%A1%E6%81%AF'
        packageMskuDetails:
          type: array
          description: 包裹MSKU明细
          items:
            $ref: '#/components/schemas/%E5%8C%85%E8%A3%B9MSKU%E6%98%8E%E7%BB%86'
      title: TemuShipmentOpenVO
      x-apifox-orders:
        - id
        - shipmentOrderSn
        - pickingListOrderSn
        - productPicture
        - productName
        - productSkcId
        - skcExtCode
        - firstOrder
        - vmiOrder
        - jitOrder
        - urgencyOrder
        - latestDeliverTime
        - deliverLimitStatus
        - latestArrivalTime
        - arrivalLimitStatus
        - shopId
        - shopName
        - deliverMethod
        - deliverMethodDesc
        - expressNo
        - expressCompanyName
        - pickupTime
        - driverName
        - carNumber
        - driverPhone
        - deliverNumber
        - deliverWarehouse
        - receiveWarehouseName
        - deliverBatchSn
        - packageTotalNum
        - deliverPackageNum
        - receivePackageNum
        - deliverTime
        - receiveTime
        - inboundTime
        - remark
        - shipmentStatus
        - shipmentStatusDesc
        - isPrintBoxMark
        - ifCanOperateDeliver
        - exitsLackOrSoldNum
        - deliverOrderSnList
        - deliverInfo
        - receiverInfo
        - packageInfoList
        - packageMskuDetails
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    包裹MSKU明细:
      type: object
      properties:
        productSkuId:
          type: integer
          format: int64
          description: 'MSKU '
        productSkuExtCode:
          type: string
          description: sku货号
        productSkuProperty:
          type: string
          description: sku属性信息
        skuNum:
          type: integer
          format: int32
          description: sku数量
        realReceiveQuantity:
          type: integer
          format: int32
          description: sku实际签收数量
        inStockQuantity:
          type: integer
          format: int32
          description: 入库数量
      title: 包裹MSKU明细
      x-apifox-orders:
        - productSkuId
        - productSkuExtCode
        - productSkuProperty
        - skuNum
        - realReceiveQuantity
        - inStockQuantity
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    包裹信息:
      type: object
      properties:
        packageSn:
          type: string
          description: 包裹号
        skcNum:
          type: integer
          format: int32
          description: 包裹数量
      title: 包裹信息
      x-apifox-orders:
        - packageSn
        - skcNum
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    收货地址信息:
      type: object
      properties:
        receiver:
          type: string
          description: 收货人姓名
        receiverPhone:
          type: string
          description: 收货人手机号
        province:
          type: string
          description: 省份
        city:
          type: string
          description: 城市
        region:
          type: string
          description: 区县
        address:
          type: string
          description: 详细地址
      title: 收货地址信息
      x-apifox-orders:
        - receiver
        - receiverPhone
        - province
        - city
        - region
        - address
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    发货地址信息:
      type: object
      properties:
        province:
          type: string
          description: 省份
        city:
          type: string
          description: 城市
        region:
          type: string
          description: 区县
        address:
          type: string
          description: 详细地址
      title: 发货地址信息
      x-apifox-orders:
        - province
        - city
        - region
        - address
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
