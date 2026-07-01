# 小时报告-SD投放报告

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/cpc/hourData/sdTarget.json:
    post:
      summary: 小时报告-SD投放报告
      deprecated: false
      description: ''
      operationId: sdTargetUsingPOST_1
      tags:
        - 广告/小时维度报告
        - 广告-小时维度报告
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
              $ref: '#/components/schemas/FeedHourDataSdTargetReqVo'
      responses:
        '200':
          description: OK
          content:
            '*/*':
              schema:
                $ref: >-
                  #/components/schemas/OpenResult%C2%ABFeedHourDataBaseRespVo%C2%ABSdAdTargetDataItem%C2%BB%C2%BB
          headers: {}
          x-apifox-name: 成功
        '201':
          description: Created
          headers: {}
          x-apifox-name: 成功
        '401':
          description: Unauthorized
          headers: {}
          x-apifox-name: 没有权限
        '403':
          description: Forbidden
          headers: {}
          x-apifox-name: 禁止访问
        '404':
          description: Not Found
          headers: {}
          x-apifox-name: 记录不存在
      security: []
      x-order: '13'
      x-apifox-folder: 广告/小时维度报告
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/1827046/apis/api-352957027-run
components:
  schemas:
    FeedHourDataSdTargetReqVo:
      type: object
      required:
        - aggregationType
        - shopId
        - date
        - campaignId
      properties:
        aggregationType:
          type: string
          description: 报告聚合类型, 投放维度:target, 广告产品+投放维度:adProductTarget
        shopId:
          type: string
          description: 店铺ID
        date:
          type: string
          description: 报告日期, 格式:yyyy-MM-dd, 只能查询最近60天
        campaignId:
          type: string
          description: 广告活动ID, 该值可从【广告-基础数据】sp/sb/sd广告活动接口的返回结果中获取(campaignId)
      title: FeedHourDataSdTargetReqVo
      x-apifox-orders:
        - aggregationType
        - shopId
        - date
        - campaignId
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    OpenResult«FeedHourDataBaseRespVo«SdAdTargetDataItem»»:
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
            #/components/schemas/FeedHourDataBaseRespVo%C2%ABSdAdTargetDataItem%C2%BB
        ts:
          type: integer
          format: int64
          description: 响应时间戳
      title: OpenResult«FeedHourDataBaseRespVo«SdAdTargetDataItem»»
      x-apifox-orders:
        - requestId
        - code
        - msg
        - data
        - ts
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    FeedHourDataBaseRespVo«SdAdTargetDataItem»:
      type: object
      properties:
        totalCount:
          type: string
          description: 总条数
        itemList:
          type: array
          description: 数据集
          items:
            $ref: '#/components/schemas/SdAdTargetDataItem'
      title: FeedHourDataBaseRespVo«SdAdTargetDataItem»
      x-apifox-orders:
        - totalCount
        - itemList
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
    SdAdTargetDataItem:
      type: object
      properties:
        groupId:
          type: string
          description: 广告组ID
        shopId:
          type: string
          description: 店铺ID
        date:
          type: string
          description: 报告日期
        targetingId:
          type: string
          description: 投放ID
        campaignId:
          type: string
          description: 广告活动ID
        targeting:
          type: string
          description: 投放值
        adId:
          type: string
          description: 广告产品ID, 当报告聚合类型aggregationType为广告产品+投放维度:adProductTarget时, 该字段有值
        portfolioId:
          type: string
          description: 广告组合ID
        hour:
          type: string
          description: 小时, HH格式, 例如:00,01,02...23, 00代表0点~1点, 01代表1点~2点...23代表23点~0点)
        msku:
          type: string
          description: 广告产品msku, 当报告聚合类型aggregationType为广告产品+投放维度:adProductTarget时, 该字段有值
        asin:
          type: string
          description: 广告产品asin, 当报告聚合类型aggregationType为广告产品+投放维度:adProductTarget时, 该字段有值
        costs:
          type: string
          description: 广告花费
        clicks:
          type: string
          description: 点击量
        impressions:
          type: string
          description: 曝光量
        sameOrders:
          type: string
          description: 本广告产品订单量
        orders:
          type: string
          description: 广告订单量
        sameSales:
          type: string
          description: 本广告产品销售额
        sales:
          type: string
          description: 广告销售额
        units:
          type: string
          description: 广告销量
        ctr:
          type: string
          description: 点击率
        cvr:
          type: string
          description: 转化率
        cpa:
          type: string
          description: 每笔订单花费
        acos:
          type: string
          description: acos
        roas:
          type: string
          description: roas
        cpc:
          type: string
          description: cpc
      title: SdAdTargetDataItem
      x-apifox-orders:
        - groupId
        - shopId
        - date
        - targetingId
        - campaignId
        - targeting
        - adId
        - portfolioId
        - hour
        - msku
        - asin
        - costs
        - clicks
        - impressions
        - sameOrders
        - orders
        - sameSales
        - sales
        - units
        - ctr
        - cvr
        - cpa
        - acos
        - roas
        - cpc
      x-apifox-ignore-properties: []
      x-apifox-folder: ''
  securitySchemes: {}
servers: []
security: []

```
