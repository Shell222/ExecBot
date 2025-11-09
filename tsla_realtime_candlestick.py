import os
import sys
import pandas as pd
from math import pi
from bokeh.plotting import figure
from bokeh.models import ColumnDataSource, Span
from bokeh.layouts import column
from bokeh.io import curdoc

# 确保能找到 user site-packages
_user_site = r"C:\Users\layu1\AppData\Roaming\Python\Python313\site-packages"
if os.path.isdir(_user_site) and _user_site not in sys.path:
    sys.path.insert(0, _user_site)

from tvDatafeed import TvDatafeed, Interval

# TradingView登录（可选）
TV_USERNAME = os.getenv("TV_USERNAME")
TV_PASSWORD = os.getenv("TV_PASSWORD")
tv = TvDatafeed(TV_USERNAME, TV_PASSWORD) if TV_USERNAME else TvDatafeed()

symbol = "TSLA"
exchange = "NASDAQ"
interval = Interval.in_1_hour
n_bars = 100

def fetch_tsla_1h():
    """获取TSLA 1小时数据"""
    try:
        print("开始从tvDatafeed获取数据...")
        df = tv.get_hist(
            symbol=symbol, 
            exchange=exchange, 
            interval=interval, 
            n_bars=n_bars, 
            extended_session=False
        )
        
        print(f"原始数据: df is None = {df is None}, df.empty = {df.empty if df is not None else 'N/A'}")
        
        if df is None or df.empty:
            print("错误: tvDatafeed返回空数据，无法获取TSLA数据")
            # 返回空的DataFrame，让调用方处理
            return pd.DataFrame(columns=["datetime", "open", "high", "low", "close"])
        
        print(f"数据列名: {df.columns.tolist()}")
        print(f"数据形状: {df.shape}")
        print(f"前3行数据:\n{df.head(3)}")
        
        df = df.reset_index()
        print(f"reset_index后列名: {df.columns.tolist()}")
        
        # 确保datetime列存在并正确转换
        if 'datetime' not in df.columns:
            print("没有datetime列，使用索引")
            df['datetime'] = df.index
        else:
            print("找到datetime列")
            
        df['datetime'] = pd.to_datetime(df['datetime'])
        print(f"时间范围: {df['datetime'].min()} 到 {df['datetime'].max()}")
        
        # 过滤交易时间（如果数据包含时间信息）
        #if not df.empty:
        #    print("开始过滤交易时间...")
        #    df = filter_trading_hours(df)
        #    print(f"过滤后数据形状: {df.shape}")
            
        return df
        
    except Exception as e:
        print(f"数据获取异常: {e}")
        import traceback
        traceback.print_exc()
        # 返回空的DataFrame，而不是模拟数据
        return pd.DataFrame(columns=["datetime", "open", "high", "low", "close"])

def filter_trading_hours(df):
    """过滤常规交易时段"""
    try:
        # 只保留美东时间09:30-16:00的数据
        df['time_only'] = df['datetime'].dt.tz_localize(None).dt.time
        start_time = pd.to_datetime("09:30").time()
        end_time = pd.to_datetime("16:00").time()
        filtered_df = df[df['time_only'].between(start_time, end_time)]
        filtered_df = filtered_df.drop('time_only', axis=1)
        return filtered_df
    except Exception as e:
        print(f"时间过滤失败: {e}")
        return df

# 持仓和订单示例（基于当前市场价格动态设置）
def get_dynamic_positions_and_orders(current_price=None):
    """根据当前价格动态生成持仓和订单位置"""
    if current_price is None:
        # 如果没有当前价格，使用默认值
        base_price = 250  # TSLA大致价格范围
    else:
        base_price = current_price
    
    positions = [
        {"price": base_price * 0.95, "label": f"买入持仓 {base_price * 0.95:.1f}", "color": "blue"},
        {"price": base_price * 1.05, "label": f"卖出持仓 {base_price * 1.05:.1f}", "color": "purple"},
    ]
    orders = [
        {"price": base_price * 0.98, "label": f"限价买单 {base_price * 0.98:.1f}", "color": "orange"},
        {"price": base_price * 1.02, "label": f"限价卖单 {base_price * 1.02:.1f}", "color": "cyan"},
    ]
    return positions, orders

# 初始化数据源
print("初始化数据源...")
df = fetch_tsla_1h()

# 检查是否成功获取数据
if df.empty:
    print("错误: 无法获取TSLA数据，请检查网络连接或tvDatafeed配置")
    # 可以选择退出程序或者显示错误信息
    # sys.exit(1)

# 动态设置持仓和订单基于实际数据
current_price = df['close'].iloc[-1] if not df.empty else None
positions, orders = get_dynamic_positions_and_orders(current_price)

print(f"初始数据加载完成，共 {len(df)} 条记录")
if not df.empty:
    print(f"最新价格: {df['close'].iloc[-1]:.2f}")
    print(f"价格范围: {df['low'].min():.2f} - {df['high'].max():.2f}")

# 创建数据源
source_all = ColumnDataSource(df)
source_inc = ColumnDataSource(df[df['close'] >= df['open']]) if not df.empty else ColumnDataSource({'datetime': [], 'open': [], 'high': [], 'low': [], 'close': []})
source_dec = ColumnDataSource(df[df['close'] < df['open']]) if not df.empty else ColumnDataSource({'datetime': [], 'open': [], 'high': [], 'low': [], 'close': []})

# 计算蜡烛宽度（带容错）
def calculate_width(df):
    if len(df) >= 2:
        try:
            delta = df['datetime'].diff().median()
            width_ms = max(delta.total_seconds() * 1000 * 0.7, 1800000)  # 至少30分钟
            return width_ms
        except:
            pass
    return 60 * 60 * 1000  # 默认1小时

width_ms = calculate_width(df) if not df.empty else 60 * 60 * 1000

# 创建K线图
p = figure(
    x_axis_type="datetime", 
    title=f"TSLA 1h Candlestick (Last Update: {pd.Timestamp.now().strftime('%H:%M:%S')})", 
    width=1000, 
    height=600
)
p.xaxis.major_label_orientation = pi/4
p.grid.grid_line_alpha = 0.3

# 绘制K线（只有在有数据时）
if not df.empty:
    p.segment('datetime', 'high', 'datetime', 'low', color="black", source=source_all)
    p.vbar(
        x='datetime', 
        width=width_ms, 
        top='close', 
        bottom='open', 
        fill_color="#26a69a",  # 绿色
        line_color="black", 
        source=source_inc
    )
    p.vbar(
        x='datetime', 
        width=width_ms, 
        top='open', 
        bottom='close', 
        fill_color="#ef5350",  # 红色
        line_color="black", 
        source=source_dec
    )
else:
    # 如果没有数据，显示提示信息
    from bokeh.models import Label
    no_data_label = Label(x=0, y=0, x_units='screen', y_units='screen',
                         text='无法获取TSLA数据，请检查网络连接',
                         text_color='red', text_font_size='16px')
    p.add_layout(no_data_label)

# 绘制持仓和订单水平线
for pos in positions:
    span = Span(
        location=pos["price"], 
        dimension='width', 
        line_color=pos["color"], 
        line_dash='dashed', 
        line_width=2
    )
    p.add_layout(span)
    # 添加标签
    from bokeh.models import Label
    label_x = df['datetime'].iloc[0] if not df.empty else pd.Timestamp.now()
    label = Label(
        x=label_x,
        y=pos["price"],
        text=pos["label"],
        text_color=pos["color"],
        y_offset=10
    )
    p.add_layout(label)

for order in orders:
    span = Span(
        location=order["price"], 
        dimension='width', 
        line_color=order["color"], 
        line_dash='dotdash', 
        line_width=2
    )
    p.add_layout(span)

# 实时更新函数
def update():
    try:
        print(f"更新数据: {pd.Timestamp.now().strftime('%H:%M:%S')}")
        new_df = fetch_tsla_1h()
        
        if new_df.empty:
            print("更新失败: 未获取到新数据")
            return
        
        # 正确更新数据源
        source_all.data = {
            'datetime': new_df['datetime'],
            'open': new_df['open'],
            'high': new_df['high'],
            'low': new_df['low'],
            'close': new_df['close']
        }
        
        # 更新涨跌数据源
        inc_df = new_df[new_df['close'] >= new_df['open']]
        dec_df = new_df[new_df['close'] < new_df['open']]
        
        source_inc.data = {
            'datetime': inc_df['datetime'],
            'open': inc_df['open'],
            'high': inc_df['high'],
            'low': inc_df['low'],
            'close': inc_df['close']
        }
        
        source_dec.data = {
            'datetime': dec_df['datetime'],
            'open': dec_df['open'],
            'high': dec_df['high'],
            'low': dec_df['low'],
            'close': dec_df['close']
        }
        
        # 动态更新持仓和订单位置
        current_price = new_df['close'].iloc[-1]
        positions, orders = get_dynamic_positions_and_orders(current_price)
        
        # 更新图表标题
        p.title.text = f"TSLA 1h Candlestick (Last Update: {pd.Timestamp.now().strftime('%H:%M:%S')}, 最新价: {current_price:.2f})"
        
        print(f"数据更新完成，当前数据量: {len(new_df)}, 最新价格: {current_price:.2f}")
        
    except Exception as e:
        print(f"更新失败: {e}")

# 添加一些调试信息
print("启动Bokeh服务器...")

# 每60秒自动刷新一次
curdoc().add_periodic_callback(update, 60000)
curdoc().add_root(column(p))
curdoc().title = "TSLA实时K线图"

print("Bokeh应用启动完成")