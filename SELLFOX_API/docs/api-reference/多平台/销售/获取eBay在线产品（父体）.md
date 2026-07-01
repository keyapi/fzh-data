# 获取eBay在线产品（父体）

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/multiplatform/ebay/product/getParentPageList.json:
    post:
      summary: 获取eBay在线产品（父体）
      deprecated: false
      description: 用户获取自身eBay店铺的父体产品信息
      operationId: getParentPageListUsingPOST_1
      tags:
        - 多平台/销售
        - eBay在线产品
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
              $ref: '#/components/schemas/EbayProductParentPageListOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABPage%C2%ABEbayProductParentPageListOpenVo%C2%BB%C2%BB
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
      x-apifox-folder: 多平台/销售
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-421782544-run
components:
  schemas:
    EbayProductParentPageListOpenQo:
      type: object
      required:
        - dateType
        - startDate
        - endDate
      properties:
        pageNo:
          type: string
          description: 第几页，默认第一页，从1开始
          examples:
            - 1
        pageSize:
          type: string
          description: 每页条数，默认100，最大支持1000
          examples:
            - 100
        shopIdList:
          type: array
          description: 店铺ID列表，最多50个
          items:
            type: string
        dateType:
          type: string
          description: 时间类型，createDate:创建日期 updateDate:更新日期
          enum:
            - createDate
            - updateDate
          examples:
            - updateDate
        startDate:
          type: string
          description: 开始日期（包含），格式：yyyy-MM-dd，与结束日期间隔不超过30天
          examples:
            - '2026-01-01'
        endDate:
          type: string
          description: 结束日期（包含），格式：yyyy-MM-dd，必须晚于或等于开始日期
          examples:
            - '2026-01-31'
      title: EbayProductParentPageListOpenQo
      x-apifox-orders:
        - pageNo
        - pageSize
        - shopIdList
        - dateType
        - startDate
        - endDate
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«Page«EbayProductParentPageListOpenVo»»:
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
          $ref: '#/components/schemas/Page%C2%ABEbayProductParentPageListOpenVo%C2%BB'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«Page«EbayProductParentPageListOpenVo»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    Page«EbayProductParentPageListOpenVo»:
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
            $ref: '#/components/schemas/EbayProductParentPageListOpenVo'
      title: Page«EbayProductParentPageListOpenVo»
      x-apifox-orders:
        - pageNo
        - pageSize
        - totalPage
        - totalSize
        - rows
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    EbayProductParentPageListOpenVo:
      type: object
      properties:
        parentId:
          type: string
          description: 父体Id
        shopId:
          type: string
          description: 店铺Id
        shopName:
          type: string
          description: 店铺名称
        hasVariation:
          type: string
          description: 是否有变种
        listingStatus:
          type: string
          description: '商品状态: Active:在线 Completed:售出 End:未卖出 EbayRemoved:移除'
        imageUrls:
          type: string
          description: 主图 多图之间,分隔
        title:
          type: string
          description: 标题
        site:
          type: string
          description: 站点
        isFixedPrice:
          type: string
          description: 是否固价
        createTime:
          type: string
          description: 创建时间
        updateTime:
          type: string
          description: 更新时间
      title: EbayProductParentPageListOpenVo
      x-apifox-orders:
        - parentId
        - shopId
        - shopName
        - hasVariation
        - listingStatus
        - imageUrls
        - title
        - site
        - isFixedPrice
        - createTime
        - updateTime
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
