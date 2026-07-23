# 获取Amazon长期仓储费报告

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/report/getFbaLongStorageFeePage.json:
    post:
      summary: 获取Amazon长期仓储费报告
      deprecated: false
      description: ''
      operationId: getFbaLongStorageFeePageUsingPOST
      tags:
        - 报告中心/报表管理
        - 数据
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
              $ref: '#/components/schemas/ReportPageOpenQo'
            example: ''
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABPage%C2%ABReportFbaLongStorageFeeOpenVo%C2%BB%C2%BB
          headers: {}
          x-apifox-name: OK
        '201':
          description: ''
          content:
            application/json:
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: Created
        '401':
          description: ''
          content:
            application/json:
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: Unauthorized
        '403':
          description: ''
          content:
            application/json:
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: Forbidden
        '404':
          description: ''
          content:
            application/json:
              schema:
                type: object
                properties: {}
                x-apifox-orders: []
                x-apifox-ignore-properties: []
          headers: {}
          x-apifox-name: Not Found
      security: []
      x-apifox-folder: 报告中心/报表管理
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-51516606-run
components:
  schemas:
    ReportPageOpenQo:
      type: object
      required:
        - startTime
        - endTime
      properties:
        pageNo:
          type: string
          description: 第几页
        pageSize:
          type: string
          description: 每页大小
        searchType:
          type: string
          description: 搜索类型(支持搜索类型:asin,msku,fnsku)
        shopIdList:
          type: array
          description: 店铺ID
          items:
            type: string
        searchContentList:
          type: array
          description: 搜索内容
          items:
            type: string
        startTime:
          type: string
          description: 开始时间(查询时间范围不能超过一年)
        endTime:
          type: string
          description: 结束时间(查询时间范围不能超过一年)
      title: ReportPageOpenQo
      x-apifox-orders:
        - pageNo
        - pageSize
        - searchType
        - shopIdList
        - searchContentList
        - startTime
        - endTime
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«Page«ReportFbaLongStorageFeeOpenVo»»:
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
          $ref: '#/components/schemas/Page%C2%ABReportFbaLongStorageFeeOpenVo%C2%BB'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«Page«ReportFbaLongStorageFeeOpenVo»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    Page«ReportFbaLongStorageFeeOpenVo»:
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
            $ref: '#/components/schemas/ReportFbaLongStorageFeeOpenVo'
      title: Page«ReportFbaLongStorageFeeOpenVo»
      x-apifox-orders:
        - pageNo
        - pageSize
        - totalPage
        - totalSize
        - rows
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    ReportFbaLongStorageFeeOpenVo:
      type: object
      properties:
        sellerId:
          type: string
          description: sellerId
        shopId:
          type: string
          description: shopId
        marketplaceId:
          type: string
          description: 站点id
        snapshotDate:
          type: string
          description: 原始日期
        convSnapshotDate:
          type: string
          description: 转换后的日期
        mskuList:
          type: array
          description: MSKU集合
          items:
            type: string
        sku:
          type: string
          description: sku
        asin:
          type: string
          description: asin
        fnsku:
          type: string
          description: FBA仓库sku
        condition:
          type: string
          description: condition
        qtyCharged12MoLongTermStorageFee:
          type: string
          description: qtyCharged12MoLongTermStorageFee
        perUnitVolume:
          type: string
          description: perUnitVolume
        currency:
          type: string
          description: 币种
        mo12LongTermsStorageFee:
          type: string
          description: mo12LongTermsStorageFee
        qtyCharged6moLongTermStorageFee:
          type: string
          description: qtyCharged6moLongTermStorageFee
        mo6longTermsStorageFee:
          type: string
          description: mo6longTermsStorageFee
        volumeUnit:
          type: string
          description: volumeUnit
        country:
          type: string
          description: 国家
        enrolledInSmallAndLight:
          type: string
          description: enrolledInSmallAndLight
        surchargeAgeTier:
          type: string
          description: 附加费库龄分段
        createTime:
          type: string
          description: 创建时间
        upStringTime:
          type: string
          description: 更新时间
      title: ReportFbaLongStorageFeeOpenVo
      x-apifox-orders:
        - sellerId
        - shopId
        - marketplaceId
        - snapshotDate
        - convSnapshotDate
        - mskuList
        - sku
        - asin
        - fnsku
        - condition
        - qtyCharged12MoLongTermStorageFee
        - perUnitVolume
        - currency
        - mo12LongTermsStorageFee
        - qtyCharged6moLongTermStorageFee
        - mo6longTermsStorageFee
        - volumeUnit
        - country
        - enrolledInSmallAndLight
        - surchargeAgeTier
        - createTime
        - upStringTime
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
