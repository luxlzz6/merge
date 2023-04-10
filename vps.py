# 打开原始文件
with open('original.txt', 'r') as f1:
    # 读取第一行数据
    first_line = f1.readline().strip()

# 关闭原始文件
f1.close()

# 如果新文件已存在，则清空文件内容
with open('new.txt', 'w') as f2:
    f2.truncate(0)

# 打开新文件，将第一行数据写入文件
with open('new.txt', 'w') as f2:
    f2.write(first_line)

# 关闭新文件
f2.close()

# 打开原始文件，跳过第一行数据，读取剩余数据
with open('original.txt', 'r') as f1:
    f1.readline()
    remaining_data = f1.read()

# 关闭原始文件
f1.close()

# 将剩余数据重新写回原始文件
with open('original.txt', 'w') as f1:
    f1.write(remaining_data)

# 关闭原始文件
f1.close()
