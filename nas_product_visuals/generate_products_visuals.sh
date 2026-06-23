#!/bin/bash
# 生成产品信息目录下各产品分类文件夹路径列表（优化版）
# 部署到群晖NAS后，请根据实际路径修改 OUTPUT_FILE 及 BASE_PATH

OUTPUT_FILE="/volume1/FZH共享文件夹/folder_paths_simple.txt"
BASE_PATH="/volume1/产品信息"

echo "开始扫描分类文件夹路径..."

# 清空输出文件
> "$OUTPUT_FILE"

# 生成报告头
{
  echo "📁 产品信息目录分类文件夹路径列表"
  echo "================================"
  echo "生成时间: $(date)"
  echo "基础路径: $BASE_PATH"
  echo ""
} >> "$OUTPUT_FILE"

# 检查基础目录是否存在
if [ ! -d "$BASE_PATH" ]; then
    echo "基础目录不存在: $BASE_PATH" | tee -a "$OUTPUT_FILE"
    exit 1
fi

TOTAL_COUNT=0

# 分别扫描 图片、视频、设计稿、调研报告 四个分类
for cat in "图片" "视频" "设计稿" "调研报告"; do
    # 找出所有存在实际文件的目录路径（递归无限深度，排除 @eaDir）
    # 逻辑：先找到所有文件，再提取其所有祖先目录（到分类文件夹自身），去重后即为"有叶子的目录"
    CAT_PATHS=$(find "$BASE_PATH" -maxdepth 2 -type d -name "$cat" -print0 | while IFS= read -r -d '' cdir; do
        find "$cdir" -type d -name "@eaDir" -prune -o -type f -print | while IFS= read -r f; do
            d=$(dirname "$f")
            while [ "$d" != "$cdir" ]; do
                echo "$d"
                d=$(dirname "$d")
            done
            echo "$cdir"
        done
    done | sort -u)

    # 处理空结果防止 wc -l 误计为 1
    if [ -z "$CAT_PATHS" ]; then
        CAT_COUNT=0
    else
        CAT_COUNT=$(echo "$CAT_PATHS" | wc -l)
    fi

    {
        echo "${cat}目录路径:"
        echo "----------------"
        if [ -n "$CAT_PATHS" ]; then
            echo "$CAT_PATHS"
        else
            echo "（无）"
        fi
        echo ""
        echo "${cat}文件夹数量: $CAT_COUNT"
        echo ""
    } >> "$OUTPUT_FILE"

    TOTAL_COUNT=$((TOTAL_COUNT + CAT_COUNT))
done

echo "扫描完成: $(date)" | tee -a "$OUTPUT_FILE"
echo "输出文件: $OUTPUT_FILE" | tee -a "$OUTPUT_FILE"
echo "各分类文件夹总数: $TOTAL_COUNT" >> "$OUTPUT_FILE"
echo "总计生成路径行数: $(wc -l < "$OUTPUT_FILE")" | tee -a "$OUTPUT_FILE"
