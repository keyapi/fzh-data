# 获取AliExpress在线产品（子体）

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/multiplatform/aliexpress/product/getChildInfo.json:
    post:
      summary: 获取AliExpress在线产品（子体）
      deprecated: false
      description: 用户获取自身AliExpress店铺的子体产品信息
      operationId: getChildInfoUsingPOST
      tags:
        - 多平台/销售
        - AliExpress在线产品
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
              $ref: '#/components/schemas/AliexpressProductChildInfoOpenQo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABList%C2%ABAliexpressProductChildListOpenVo%C2%BB%C2%BB
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
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-421782541-run
components:
  schemas:
    AliexpressProductChildInfoOpenQo:
      type: object
      properties:
        productId:
          type: string
        shopId:
          type: string
      title: AliexpressProductChildInfoOpenQo
      x-apifox-orders:
        - productId
        - shopId
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«List«AliexpressProductChildListOpenVo»»:
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
          type: array
          description: 数据
          items:
            $ref: '#/components/schemas/AliexpressProductChildListOpenVo'
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«List«AliexpressProductChildListOpenVo»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    AliexpressProductChildListOpenVo:
      type: object
      properties:
        shopId:
          type: string
          description: 店铺Id
        shopName:
          type: string
          description: 店铺名称
        shopType:
          type: string
          description: >-
            店铺类型: POP_CHOICE:POP与半托管店铺 ONE_STOP_SERVICE:全托管店铺
            LOCAL_SERVICE:海外托管店铺
        productId:
          type: string
          description: ProductId
        skuId:
          type: string
          description: skuId
        msku:
          type: string
          description: msku
        salesmanNameList:
          type: array
          description: 业务员名称列表
          items:
            type: string
        productPrice:
          type: string
          description: 全托/海外托管:供货价 自营/半托:零售价
        mskuImage:
          type: string
          description: 子图 多图之间,分隔
        propertyValueDefinitionName:
          type: string
          description: 属性值自定义名称
        skuPropertyName:
          type: string
          description: 属性值名称
        mskuDiscountPrice:
          type: string
          description: 折扣价格 仅POP/半托管
        status:
          type: string
          description: >-
            平台销售状态 全托/海托:
            active(销售);inactive(不销售)。自营/半托:onSelling（正在销售），offline（已下架），auditing（审核中），editingRequired（审核不通过）
        skuStock:
          type: string
          description: 库存数
        matchStatus:
          type: string
          description: 是否配对 0未配对，1已配对
        commoditySku:
          type: string
          description: 配对商品Sku
        commodityName:
          type: string
          description: 配对商品名称
        createTime:
          type: string
          description: 创建时间
        updateTime:
          type: string
          description: 更新时间
      title: AliexpressProductChildListOpenVo
      x-apifox-orders:
        - shopId
        - shopName
        - shopType
        - productId
        - skuId
        - msku
        - salesmanNameList
        - productPrice
        - mskuImage
        - propertyValueDefinitionName
        - skuPropertyName
        - mskuDiscountPrice
        - status
        - skuStock
        - matchStatus
        - commoditySku
        - commodityName
        - createTime
        - updateTime
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
