# 获取FBA货件列表

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/inbound/shipment/page.json:
    post:
      summary: 获取FBA货件列表
      deprecated: false
      description: ''
      operationId: shipmentPageUsingPOST
      tags:
        - FBA/FBA货件（STA）
        - STA货件
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
              $ref: '#/components/schemas/InboundShipmentPageOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABPage%C2%ABInboundShipmentPageOpenVo%C2%BB%C2%BB
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
      x-apifox-folder: FBA/FBA货件（STA）
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-484698677-run
components:
  schemas:
    InboundShipmentPageOpenQo:
      type: object
      properties:
        shopIds:
          type: array
          description: 店铺ID
          items:
            type: integer
            format: int32
        marketplaceIds:
          type: array
          description: 站点
          items:
            type: string
        status:
          type: array
          description: >-
            货件状态，可选值：WORKING、READY_TO_SHIP、SHIPPED、IN_TRANSIT、DELIVERED、CHECKED_IN、RECEIVING、CLOSED、CANCELLED、DELETED、ABANDONED、CREATING、MIXED、UNCONFIRMED
          items:
            type: string
        amazonShipmentIds:
          type: array
          description: 货件编号
          items:
            type: string
        createTimeStart:
          type: string
          description: 创建开始时间，yyyy-MM-dd HH:mm:ss，创建时间范围最长不超过360天，创建时间范围和更新时间范围必须至少传递一组完整区间
          examples:
            - '2026-01-01 00:00:00'
        createTimeEnd:
          type: string
          description: 创建结束时间，yyyy-MM-dd HH:mm:ss，创建时间范围最长不超过360天
          examples:
            - '2026-05-30 23:59:59'
        updateTimeStart:
          type: string
          description: 更新开始时间，yyyy-MM-dd HH:mm:ss，更新时间范围最长不超过360天，更新时间范围和创建时间范围必须至少传递一组完整区间
          examples:
            - '2026-01-01 00:00:00'
        updateTimeEnd:
          type: string
          description: 更新结束时间，yyyy-MM-dd HH:mm:ss，更新时间范围最长不超过360天
          examples:
            - '2026-05-30 23:59:59'
        pageNo:
          type: string
          description: 第几页
        pageSize:
          type: string
          description: 每页大小
      title: InboundShipmentPageOpenQo
      description: FBA货件列表查询参数
      x-apifox-orders:
        - shopIds
        - marketplaceIds
        - status
        - amazonShipmentIds
        - createTimeStart
        - createTimeEnd
        - updateTimeStart
        - updateTimeEnd
        - pageNo
        - pageSize
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«Page«InboundShipmentPageOpenVo»»:
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
          $ref: '#/components/schemas/Page%C2%ABInboundShipmentPageOpenVo%C2%BB'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«Page«InboundShipmentPageOpenVo»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    Page«InboundShipmentPageOpenVo»:
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
            $ref: '#/components/schemas/InboundShipmentPageOpenVo'
      title: Page«InboundShipmentPageOpenVo»
      x-apifox-orders:
        - pageNo
        - pageSize
        - totalPage
        - totalSize
        - rows
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    InboundShipmentPageOpenVo:
      type: object
      properties:
        id:
          type: integer
          format: int64
          description: ID
        shopId:
          type: integer
          format: int32
          description: 店铺ID
        marketplaceId:
          type: string
          description: 站点
        inboundPlanId:
          type: string
          description: 工作流编号
        amazonShipmentId:
          type: string
          description: 货件编号
        shipmentId:
          type: string
          description: 货件ID
        name:
          type: string
          description: 货件名称
        source: &ref_1
          $ref: '#/components/schemas/FbaAddressOpenVo'
        fulfillmentCenterId:
          type: string
          description: 仓库编码
        shipmentDestination: &ref_0
          $ref: '#/components/schemas/ShipmentDestination'
        editShipmentDestination: *ref_0
        status:
          type: string
          description: >-
            货件状态
            （WORKING、READY_TO_SHIP、SHIPPED、IN_TRANSIT、DELIVERED、CHECKED_IN、RECEIVING、CLOSED、CANCELLED、DELETED、ABANDONED、CREATING、MIXED、UNCONFIRMED）
        transitStatus:
          type: integer
          format: int32
          description: 货件模式，货件是否算在途（0 不计算在途，1 计算在途）
        transitStatusForShipOrder:
          type: integer
          format: int32
          description: 发货单模式，货件是否算在途（0 不计算在途，1 计算在途）
        shipmentType:
          type: integer
          format: int32
          description: 货件类型（0 普通货件 1 AWD转移货件）
        shippingSolution:
          type: string
          description: 承运人类型（AMAZON_PARTNERED_CARRIER 亚马逊合作承运人、USE_YOUR_OWN_CARRIER 非合作承运人）
        carrierName:
          type: string
          description: 承运人
        cartonNum:
          type: integer
          format: int32
          description: 箱子数量
        shippedDate:
          type: string
          format: date-time
          description: 发货时间
        remark:
          type: string
          description: 备注
        createId:
          type: integer
          format: int32
          description: 创建人ID
        createName:
          type: string
          description: 创建人
        createTime:
          type: string
          format: date-time
          description: 创建时间
        updateTime:
          type: string
          format: date-time
          description: 更新时间
        mobile:
          type: string
          description: 发件地址电话
        trackNos:
          type: array
          description: 运单号
          items:
            type: string
        shipSnList:
          type: array
          description: 发货单号列表
          items:
            type: string
        weight:
          type: number
          format: double
          description: 重量
        volume:
          type: number
          format: double
          description: 体积
        createBy:
          type: integer
          format: int32
          description: 创建来源（0 亚马逊 1 赛狐）
        referenceId:
          type: string
          description: referenceId
        factoryDirect:
          type: integer
          format: int32
          description: 工厂直发（0否 1是）
      title: InboundShipmentPageOpenVo
      description: 新版FBA货件列表
      x-apifox-orders:
        - id
        - shopId
        - marketplaceId
        - inboundPlanId
        - amazonShipmentId
        - shipmentId
        - name
        - source
        - fulfillmentCenterId
        - shipmentDestination
        - editShipmentDestination
        - status
        - transitStatus
        - transitStatusForShipOrder
        - shipmentType
        - shippingSolution
        - carrierName
        - cartonNum
        - shippedDate
        - remark
        - createId
        - createName
        - createTime
        - updateTime
        - mobile
        - trackNos
        - shipSnList
        - weight
        - volume
        - createBy
        - referenceId
        - factoryDirect
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ShipmentDestination:
      type: object
      properties:
        destination: *ref_1
        fulfillmentCenterId:
          type: string
          description: 仓库编码
      title: ShipmentDestination
      description: 收货信息
      x-apifox-orders:
        - destination
        - fulfillmentCenterId
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FbaAddressOpenVo:
      type: object
      properties:
        name:
          type: string
          description: 姓名
        addressLine1:
          type: string
          description: 地址1
        addressLine2:
          type: string
          description: 地址2
        city:
          type: string
          description: 城市
        districtOrCounty:
          type: string
          description: 国家或地区
        stateOrProvinceCode:
          type: string
          description: 州省
        countryCode:
          type: string
          description: 国家代码
        postalCode:
          type: string
          description: 邮编
        email:
          type: string
          description: 电子邮件
        phoneNumber:
          type: string
          description: 电话号码
        companyName:
          type: string
          description: 公司名称
      title: FbaAddressOpenVo
      description: FBA地址信息：source寄件地址 destination收件地址
      x-apifox-orders:
        - name
        - addressLine1
        - addressLine2
        - city
        - districtOrCounty
        - stateOrProvinceCode
        - countryCode
        - postalCode
        - email
        - phoneNumber
        - companyName
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
