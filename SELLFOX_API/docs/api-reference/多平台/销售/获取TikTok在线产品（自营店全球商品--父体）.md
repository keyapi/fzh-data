# 获取TikTok在线产品（自营店全球商品--父体）

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/multiplatform/tiktok/global/product/getParentPageList.json:
    post:
      summary: 获取TikTok在线产品（自营店全球商品--父体）
      deprecated: false
      description: 用户获取自身TikTok店铺（自营店全球商品）的父体产品信息
      operationId: getParentPageListUsingPOST_7
      tags:
        - 多平台/销售
        - TTiKTok自营全球商品
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
              $ref: '#/components/schemas/TiKTokGlobalProductParentPageListOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABPage%C2%ABTiktokGlobalProductPageListOpenVo%C2%BB%C2%BB
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-421782556-run
components:
  schemas:
    TiKTokGlobalProductParentPageListOpenQo:
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
      title: TiKTokGlobalProductParentPageListOpenQo
      x-apifox-orders:
        - pageNo
        - pageSize
        - shopIdList
        - dateType
        - startDate
        - endDate
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«Page«TiktokGlobalProductPageListOpenVo»»:
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
          $ref: >-
            #/components/schemas/Page%C2%ABTiktokGlobalProductPageListOpenVo%C2%BB
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«Page«TiktokGlobalProductPageListOpenVo»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    Page«TiktokGlobalProductPageListOpenVo»:
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
            $ref: '#/components/schemas/TiktokGlobalProductPageListOpenVo'
      title: Page«TiktokGlobalProductPageListOpenVo»
      x-apifox-orders:
        - pageNo
        - pageSize
        - totalPage
        - totalSize
        - rows
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    TiktokGlobalProductPageListOpenVo:
      type: object
      properties:
        parentId:
          type: string
          description: 父体id
        shopId:
          type: string
          description: 店铺id
        shopName:
          type: string
          description: 店铺名称
        globalSellerId:
          type: string
          description: 全球店铺sellerId
        globalProductId:
          type: string
          description: 平台产品id（父体）
        productName:
          type: string
          description: 产品名称
        tkStatus:
          type: string
          description: 已发布  已创建  草稿  已删除
        mainImage:
          type: string
          description: 主图
        publishSiteList:
          type: array
          description: 已发布站点
          items:
            type: string
        platformCreateTime:
          type: string
          description: 平台创建时间
        platformUpdateTime:
          type: string
          description: 平台更新时间
        productSyncTime:
          type: string
          description: 产品同步时间
      title: TiktokGlobalProductPageListOpenVo
      x-apifox-orders:
        - parentId
        - shopId
        - shopName
        - globalSellerId
        - globalProductId
        - productName
        - tkStatus
        - mainImage
        - publishSiteList
        - platformCreateTime
        - platformUpdateTime
        - productSyncTime
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
