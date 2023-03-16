#!/usr/bin/env python3

import os, re, subprocess
import argparse, configparser
import base64, yaml
import socket
import geoip2.database
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
import requests


def convert(subscription, target, other_config={}):
    """Wrapper for subconverter
    subscription: subscription url or content string or local file path, add url support.
    target: target subconvert configuration
    other_config:
        deduplicate: whether to deduplicate
        keep_nodes: amounts of nodes to keep when they are deduplicated
        include: include string in remark
        exclude: exclude string in remark
        config: output subcription config
    """

    default_config = {
        'target': target,
        'deduplicate': False, 'keep_nodes': 1,
        'rename': '', 'include': '', 'exclude': '', 'config': ''
    }
    default_config.update(other_config)
    config = default_config

    work_dir = os.getcwd()
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    if subscription[:8] == 'https://':
        clash_provider = subconverterhandler(subscription)
    else:
        try:
            with open(subscription, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'proxies:' not in content and '://' in content:
                    subscription = content
                    raise ValueError
                else:
                    clash_provider = subconverterhandler(subscription)
        except Exception:
            try:
                if 'proxies:' not in subscription:
                    if '://' in subscription:
                        subscription = base64_encode(subscription)
                        with open('./subscription', 'w', encoding='utf-8') as f:
                            f.write(subscription)
                        clash_provider = subconverterhandler('./subscription')
                        os.remove('./subscription')
                else:
                    with open('./subscription', 'w', encoding='utf-8') as f:
                        f.write(subscription)
                    clash_provider = subconverterhandler('./subscription')
                    os.remove('./subscription')
            except Exception:
                print('No nodes were found in url.')
                os.chdir(work_dir)
                return ''

    if config['deduplicate']:
        clash_provider = deduplicate(clash_provider, config['keep_nodes'])
    with open('./temp', 'w', encoding='utf-8') as temp_file:
        temp_file.write(clash_provider)
    output = subconverterhandler('./temp', config)

    os.chdir(work_dir)
    return output


def subconverterhandler(subscription,
                        input_config={'target': 'transfer', 'rename': '', 'include': '', 'exclude': '', 'config': ''}):
    """Wrapper for subconverter(by configuration file: generate.ini)
    Target handling config parameters(parameters from https://github.com/tindy2013/subconverter/blob/master/README-cn.md#%E8%BF%9B%E9%98%B6%E9%93%BE%E6%8E%A5):
        target: target subconvert configuration
        url: input subcription url or file path
        include: include string in remark
        exclude: exclude string in remark
        config: output subcription config
    Function input_config variant should be a dictionary which has keys and values of above parameters, output content will be string of target configuration.
    By default, functon will output clash_provider without any format methods.
    """
    work_dir = os.getcwd()
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    configparse = configparser.ConfigParser()
    configparse.read('./generate.ini', encoding='utf-8')

    url = subscription
    target = input_config['target']
    rename = input_config['rename']
    include = input_config['include']
    exclude = input_config['exclude']
    config = input_config['config']
    configparse.set(target, 'url', url)
    configparse.set(target, 'rename', rename)
    configparse.set(target, 'include', include)
    configparse.set(target, 'exclude', exclude)
    configparse.set(target, 'config', config)

    origin_configparse = configparser.ConfigParser()
    origin_configparse.read('./generate.ini', encoding='utf-8')
    origin_config = {'url': origin_configparse[target]['url'], 'rename': origin_configparse[target]['rename'],
                     'include': origin_configparse[target]['include'], 'exclude': origin_configparse[target]['exclude'],
                     'config': origin_configparse[target]['config']}

    with open('./generate.ini', 'w', encoding='utf-8') as ini:
        configparse.write(ini, space_around_delimiters=False)

    if os.name == 'posix':
        args = ['./subconverter-linux-amd64', '-g', '--artifact', target]
    elif os.name == 'nt':
        args = ['.\subconverter-windows-amd64.exe', '-g', '--artifact', target]
    subconverter = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True,
                                    encoding='utf-8', bufsize=1)
    logs = subconverter.stdout.readlines()
    subconverter.wait()
    # Print log
    pre_run = False
    for line in logs:
        if 'Fetching node data from url' in line and '\'./temp\'' not in line:
            pre_run = True
            print(line[:-1])
    if pre_run == False:
        if '[INFO]' not in (logs[-3]):
            print(logs[-2])
        else:
            print(logs[-3])

    if subconverter.returncode != 0:
        try:
            os.remove('./temp')
            output = ''
        except Exception:
            output = ''
    else:
        try:
            with open(f'./temp', 'r', encoding='utf-8', errors='ignore') as temp_file:
                output = ''
                while True:
                    content = temp_file.read(100)
                    if not content:
                        break
                    output += content
            if target == 'url':
                output = base64_decode(output)
            os.remove('./temp')
        except Exception:
            output = ''

    origin_configparse.set(target, 'url', origin_config['url'])
    origin_configparse.set(target, 'rename', origin_config['rename'])
    origin_configparse.set(target, 'include', origin_config['include'])
    origin_configparse.set(target, 'exclude', origin_config['exclude'])
    origin_configparse.set(target, 'config', origin_config['config'])
    with open('./generate.ini', 'w', encoding='utf-8') as ini:
        origin_configparse.write(ini, space_around_delimiters=False)

    os.chdir(work_dir)
    return output


def deduplicate(clash_provider,
                keep_nodes=1):  # Proxies deduplicate. If proxies with the same servers are greater than keep_nodes, they will not be added.
    lines = re.split(r'\n+', clash_provider)[1:]
    print('Starting deduplicate...')
    print(f'Init amount: {len(lines)}')
    try:
        proxies = yaml.safe_load(clash_provider)['proxies']  # load all proxies from clash provider
    except Exception:
        il_chars = ['|', '?', '[', ']', '@', '!', '%', ':']

        line_fixed = ['proxies:']
        for line in lines:
            try_load = 'proxies:\n' + line
            try:
                yaml.safe_load(try_load)
                line_fixed.append(line)
            except Exception:
                line = line.replace('\'', '').replace('"', '')
                value_list = re.split(r': |, ', line)
                if len(value_list) > 6:
                    value_list_fix = []
                    for value in value_list:
                        for char in il_chars:
                            value_il = False
                            if char in value:
                                value_il = True
                                break
                        if value_il == True and ('{' not in value and '}' not in value):
                            value = '"' + value + '"'
                            value_list_fix.append(value)
                        elif value_il == True and '}' in value:
                            if '}}}' in value:
                                host_part = value.replace('}}}', '')
                                host_value = '"' + host_part + '"}}}'
                                value_list_fix.append(host_value)
                            elif '}}' not in value:
                                host_part = value.replace('}', '')
                                host_value = '"' + host_part + '"}'
                                value_list_fix.append(host_value)
                        else:
                            value_list_fix.append(value)
                        line_fix = line
                    for index in range(len(value_list_fix)):
                        line_fix = line_fix.replace(value_list[index], value_list_fix[index])
                else:
                    pass
                try:
                    try_load = 'proxies:\n' + line_fix
                    yaml.safe_load(try_load)
                    line_fixed.append(line_fix)
                except Exception:
                    pass
        fix_provider = '\n'.join(line_fixed)

        try:
            proxies = yaml.safe_load(fix_provider)['proxies']
        except Exception:
            print('Deduplicate failed, skip')
            output = clash_provider
            return output

    servers = {}
    for proxy in proxies:
        server = proxy['server']  # assign remote server
        if server.replace('.', '').isdigit():
            ip = server
        else:
            try:
                ip = socket.gethostbyname(server)
            except Exception:
                ip = server

        if ip in servers:
            servers[ip].append(proxy)  # add proxy to its remote server list
        elif server not in servers:
            servers[ip] = [proxy]  # init remote server list, add first proxy

    proxies = []
  
    for server in servers:
        try:
            add_list = servers[server][:keep_nodes]
        except Exception:
            add_list = servers[server]
        for x in add_list:
            proxies.append(x)
    print(f'Dedupicate success, remove {len(lines)-len(proxies)} duplicate proxies')
    print(f'Output amount: {len(proxies)}')
    proxie = []
    proxie = name(proxies)

    output = yaml.dump({'proxies': proxie}, default_flow_style=False, sort_keys=False, allow_unicode=True, indent=2)
    return output
mapping = {'AD': '安道尔', 'AE': '阿联酋', 'AF': '阿富汗', 'AG': '安提瓜和巴布达',
           'AI': '安圭拉', 'AL': '阿尔巴尼亚', 'AM': '亚美尼亚', 'AO': '安哥拉',
           'AQ': '南极洲', 'AR': '阿根廷', 'AS': '美属萨摩亚', 'AT': '奥地利',
           'AU': '澳大利亚', 'AW': '阿鲁巴', 'AX': '奥兰群岛', 'AZ': '阿塞拜疆',
           'BA': '波斯尼亚和黑塞哥维那', 'BB': '巴巴多斯', 'BD': '孟加拉国', 'BE': '比利时',
           'BF': '布基纳法索', 'BG': '保加利亚', 'BH': '巴林', 'BI': '布隆迪',
           'BJ': '贝宁', 'BL': '圣巴泰勒米', 'BM': '百慕大', 'BN': '文莱',
           'BO': '玻利维亚', 'BQ': '博内尔岛、圣尤斯特歇斯和萨巴', 'BR': '巴西', 'BS': '巴哈马',
           'BT': '不丹', 'BV': '布维岛', 'BW': '博茨瓦纳', 'BY': '白俄罗斯',
           'BZ': '伯利兹', 'CA': '加拿大', 'CC': '科科斯（基林）群岛', 'CD': '刚果民主共和国',
           'CF': '中非共和国', 'CG': '刚果共和国', 'CH': '瑞士', 'CI': '科特迪瓦',
           'CK': '库克群岛', 'CL': '智利', 'CM': '喀麦隆', 'CN': '中国',
           'CO': '哥伦比亚', 'CR': '哥斯达黎加', 'CU': '古巴', 'CV': '佛得角',
           'CW': '库拉索', 'CX': '圣诞岛', 'CY': '塞浦路斯', 'CZ': '捷克共和国',
           'DE': '德国', 'DJ': '吉布提', 'DK': '丹麦', 'DM': '多米尼克',
           'DO': '多米尼加共和国', 'DZ': '阿尔及利亚', 'EC': '厄瓜多尔', 'EE': '爱沙尼亚',
           'EG': '埃及', 'EH': '西撒哈拉', 'ER': '厄立特里亚', 'ES': '西班牙', 'ET': '埃塞俄比亚',
           'FI': '芬兰', 'FJ': '斐济', 'FK': '福克兰群岛', 'FM': '密克罗尼西亚联邦', 'FO': '法罗群岛',
           'FR': '法国', 'GA': '加蓬', 'GB': '英国', 'GD': '格林纳达', 'GE': '格鲁吉亚',
           'GF': '法属圭亚那', 'GG': '根西岛', 'GH': '加纳', 'GI': '直布罗陀', 'GL': '格陵兰',
           'GM': '冈比亚', 'GN': '几内亚', 'GP': '瓜德罗普', 'GQ': '赤道几内亚', 'GR': '希腊',
           'GS': '南乔治亚岛和南桑威奇群岛', 'GT': '危地马拉', 'GU': '关岛', 'GW': '几内亚比绍', 'GY': '圭亚那',
           'HK': '中国香港', 'HM': '赫德岛和麦当劳群岛', 'HN': '洪都拉斯', 'HR': '克罗地亚', 'HT': '海地',
           'HU': '匈牙利', 'ID': '印度尼西亚', 'IE': '爱尔兰', 'IL': '以色列', 'IM': '马恩岛',
           'IN': '印度', 'IO': '英属印度洋领地', 'IQ': '伊拉克', 'IR': '伊朗', 'IS': '冰岛',
           'IT': '意大利', 'JE': '泽西岛', 'JM': '牙买加', 'JO': '约旦', 'JP': '日本',
           'KE': '肯尼亚', 'KG': '吉尔吉斯斯坦', 'KH': '柬埔寨', 'KI': '基里巴斯', 'KM': '科摩罗',
           'KN': '圣基茨和尼维斯', 'KP': '朝鲜', 'KR': '韩国', 'KW': '科威特', 'KY': '开曼群岛',
           'KZ': '哈萨克斯坦', 'LA': '老挝', 'LB': '黎巴嫩', 'LC': '圣卢西亚', 'LI': '列支敦士登',
           'LK': '斯里兰卡', 'LR': '利比里亚', 'LS': '莱索托', 'LT': '立陶宛', 'LU': '卢森堡',
           'LV': '拉脱维亚', 'LY': '利比亚', 'MA': '摩洛哥', 'MC': '摩纳哥', 'MD': '摩尔多瓦',
           'ME': '黑山', 'MF': '法属圣马丁', 'MG': '马达加斯加', 'MH': '马绍尔群岛', 'MK': '北马其顿',
           'ML': '马里', 'MM': '缅甸', 'MN': '蒙古', 'MO': '中国澳门', 'MP': '北马里亚纳群岛',
           'MQ': '马提尼克', 'MR': '毛里塔尼亚', 'MS': '蒙特塞拉特', 'MT': '马耳他', 'MU': '毛里求斯',
           'MV': '马尔代夫', 'MW': '马拉维', 'MX': '墨西哥', 'MY': '马来西亚', 'MZ': '莫桑比克',
           'NA': '纳米比亚', 'NC': '新喀里多尼亚', 'NE': '尼日尔', 'NF': '诺福克岛', 'NG': '尼日利亚',
           'NI': '尼加拉瓜', 'NL': '荷兰', 'NO': '挪威', 'NP': '尼泊尔', 'NR': '瑙鲁',
           'NU': '纽埃', 'NZ': '新西兰', 'OM': '阿曼', 'PA': '巴拿马', 'PE': '秘鲁',
           'PF': '法属波利尼西亚', 'PG': '巴布亚新几内亚', 'PH': '菲律宾', 'PK': '巴基斯坦', 'PL': '波兰',
           'PM': '圣皮埃尔和密克隆群岛', 'PN': '皮特凯恩群岛', 'PR': '波多黎各', 'PS': '巴勒斯坦', 'PT': '葡萄牙',
           'PW': '帕劳', 'PY': '巴拉圭', 'QA': '卡塔尔', 'RE': '留尼汪', 'RO': '罗马尼亚',
           'RS': '塞尔维亚', 'RU': '俄罗斯', 'RW': '卢旺达', 'SA': '沙特阿拉伯', 'SB': '所罗门群岛',
           'SC': '塞舌尔', 'SD': '苏丹', 'SE': '瑞典', 'SG': '新加坡', 'SH': '圣赫勒拿、阿森松和特里斯坦达库尼亚群岛',
           'SI': '斯洛文尼亚', 'SJ': '斯瓦尔巴特和扬马延', 'SK': '斯洛伐克', 'SL': '塞拉利昂', 'SM': '圣马力诺',
           'SN': '塞内加尔', 'SO': '索马里', 'SR': '苏里南', 'SS': '南苏丹', 'ST': '圣多美和普林西比',
           'SV': '萨尔瓦多', 'SX': '荷属圣马丁', 'SY': '叙利亚', 'SZ': '斯威士兰', 'TC': '特克斯和凯科斯群岛',
           'TD': '乍得', 'TG': '多哥', 'TH': '泰国', 'TJ': '塔吉克斯坦', 'TK': '托克劳',
           'TL': '东帝汶', 'TM': '土库曼斯坦', 'TN': '突尼斯', 'TO': '汤加', 'TR': '土耳其',
           'TT': '特立尼达和多巴哥', 'TV': '图瓦卢', 'TW': '台湾', 'TZ': '坦桑尼亚', 'UA': '乌克兰',
           'UG': '乌干达', 'US': '美国', 'UY': '乌拉uguay', 'UZ': '乌兹别克斯坦', 'VA': '梵蒂冈',
           'VC': '圣文森特和格林纳丁斯', 'VE': '委内瑞拉', 'VG': '英属维尔京群岛', 'VI': '美属维尔京群岛', 'VN': '越南',
           'VU': '瓦努阿图', 'WF': '瓦利斯和富图纳群岛', 'WS': '萨摩亚', 'YE': '也门', 'YT': '马约特',
           'ZA': '南非', 'ZM': '赞比亚', 'ZW': '津巴布韦',
           'RELAY': '其他', 'None': '未知'}
# 使用多线程处理所有节点
def name(servers):
    with ThreadPoolExecutor(max_workers=10) as executor:
        for node in servers:
            executor.submit(name, node)
 

# 使用多线程处理所有节点
def get_location(ip_address):
    with ThreadPoolExecutor(max_workers=10) as executor:
        for node in ip_address:
            executor.submit(name, node)
            

         

# 使用多线程处理所有节点
def resolve_address(address):
    with ThreadPoolExecutor(max_workers=10) as executor:
        for node in address:
            executor.submit(name, node)


def name(servers):
    proxies=[]
    for server in servers:
        try:
            add_list = servers[server][:keep_nodes]
        except Exception:
            add_list[server] = [servers]
        for x in add_list:
            item_name = str(x['name'])
            se = str(x['server'])
            server = resolve_address(se)
            try:
                ip_address = socket.gethostbyname(server)
            except Exception:
                ip_address = server
            ip = str(ip_address)
            try:
                ip_name = get_location(ip)
            except Exception:
                ip_name = 'None'
            for k, v in mapping.items():
                if k in ip_name:
                    item_name = v
                    break
            else:
                item_name = '其他'
            x['name'] = item_name
            x['server'] = se
            proxies.append(x)
    return proxies


def get_location(ip_address):
    # 发送HTTP请求获取IP地址归属地
    response = requests.get(f"https://ipinfo.io/{ip_address}")
    if response.status_code == 200:
        # 解析JSON格式的响应数据
        data = response.json()
        # 返回国家信息
        return data.get("country")
    else:
        return 'None'


def resolve_address(address):
    # 判断地址类型
    try:
        socket.inet_aton(address)
        # 如果是IP地址，直接返回
        return address
    except socket.error:
        # 如果不是IP地址，则转换为IP地址
        try:
            return socket.gethostbyname(address)
        except:
            return address


def base64_decode(content):
    if '-' in content:
        content = content.replace('-', '+')
    if '_' in content:
        content = content.replace('_', '/')
    # print(len(url_content))
    missing_padding = len(content) % 4
    if missing_padding != 0:
        content += '=' * (4 - missing_padding)  # 不是4的倍数后加= https://www.cnblogs.com/wswang/p/7717997.html
    try:
        base64_content = base64.b64decode(content.encode('utf-8')).decode('utf-8',
                                                                          'ignore')  # https://www.codenong.com/42339876/
        base64_content_format = base64_content
        return base64_content_format
    except UnicodeDecodeError:
        base64_content = base64.b64decode(content)
        base64_content_format = base64_content
        return str(base64_content)


def base64_encode(content):
    if content == None:
        content = ''
    base64_content = base64.b64encode(content.encode('utf-8')).decode('ascii')
    return base64_content


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Convert between various proxy subscription formats using Subconverter.')
    parser.add_argument('--subscription', '-s', help='Your subscription url or local file path.', required=True)
    parser.add_argument('--target', '-t', help='Target convert format, support base64, clash, clash_provider, quanx.',
                        default='clash')
    parser.add_argument('--output', '-o',
                        help='Target path to output, default value is the Subconverter root directionary.',
                        default='./Eternity.yaml')
    parser.add_argument('--deduplicate', '-d', help='Whether to deduplicate proxies, default value is False.',
                        default=False)
    parser.add_argument('--keep', '-k', help='Amounts of nodes to keep when deduplicated.', default=1)
    args = parser.parse_args()

    subscription = args.subscription
    target = args.target
    output_dir = args.output
    if args.deduplicate == 'true' or args.deduplicate == 'True':
        deduplicate_enabled = True
    else:
        deduplicate_enabled = False
    keep_nodes = int(args.keep)

    work_dir = os.getcwd()
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    generate = configparser.ConfigParser()
    generate.read('./generate.ini', encoding='utf-8')
    config = {'deduplicate': deduplicate_enabled, 'keep_nodes': keep_nodes, 'rename': generate.get(target, 'rename'),
              'include': generate.get(target, 'include'), 'exclude': generate.get(target, 'exclude'),
              'config': generate.get(target, 'config')}

    output = convert(subscription, target, config)

    with open(output_dir, 'w', encoding='utf-8') as temp_file:
        temp_file.write(output)
    os.chdir(work_dir)
