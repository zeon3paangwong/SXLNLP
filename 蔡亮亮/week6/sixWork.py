

# embedding层权重参数:
"""
    # 池化
    768*768
    # 2分类
    Token: 768*2
    # 位置标记
    Position: 512*768

"""
# 注意力层权重参数:
"""
    (h*h)Q: 768*768
    (h*h)K: 768*768
    (h*h)V: 768*768
    d:768*768

"""
# LayerNorm归一化权重参数:
"""
    对embedding:768*1
    对attention:768*1
    映射4倍维度:768*3072
    映射回来:3072*3072
    
"""