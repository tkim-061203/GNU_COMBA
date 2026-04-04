import glob, os, numpy as np

print(os.getcwd())
pathlist = glob.glob(".cache_count_num_cell_2/*.txt")

def mymap(x):
    with open(x, 'r') as file:
        textarr = file.read().split(',')
        # print(textarr[1])
        try:
            logic_num = int(textarr[1])
        except:
            logic_num = None
        return [int(os.path.basename(x).replace(".txt", "")), logic_num]

logic_list = np.array(list(map(mymap, pathlist)))
noneidxs = logic_list[:, 1] != None
logic_list = logic_list[noneidxs]
max_logic = np.max(logic_list[:,1])
where_max = np.where(logic_list[:, 1] == max_logic)[0]
print(max_logic, logic_list[:, 0][where_max], len(logic_list))
# for path in pathlist:
#     filename = os.path.basename(path)
#     print(filename)
#     break