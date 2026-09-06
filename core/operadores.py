import csv
from ipaddress import  IPv4Network
import networkx as nx
## DEVICES CLASES
from core.devices import (
    Device_pc as D_pc, 
    Device_switch as D_sw, 
    Device_router as D_r,
    Device_serv as D_serv
)
from collections import defaultdict, deque
import itertools

import pprint

class Operator_reader:
    def __init__(self, ruta):
        self.ruta = ruta
        ##
        self.router_true = False
        self.dic_device_type = {}
        self.dic_device_objeto = {}
        self.lista_routers = []
        self.dic_conexiones = {
            'rr': {},
            'rs': {},
            'rd': {},
            'ss': {},
            'sd': {}
        }
    def get_core(self, path: str|None = None):
        self.read_csv(path)
        return self.dic_device_type,self.dic_device_objeto, self.dic_conexiones

    def read_csv(self, path: str|None = None):
        if path is None:
            path = f"{self.ruta}/data/conexiones.csv"
        with open(path, mode='r', newline='', encoding='utf-8') as conexiones:
            reader = csv.reader(conexiones)
            
            for num_line, line in enumerate(reader, start=1):
                if len(line) != 3:
                    print(f"Error en la línea {num_line}")
                    continue
                dev1,x,dev2 = line
                device1, tipo1 = dev1.split(":")
                device2, tipo2 = dev2.split(":")  

                if self.dic_device_type.get(device1) is None:
                    self.dic_device_type[device1] = tipo1
                    self.tipo_dispositivo(device1, tipo1)
                if device2!="None":
                    if self.dic_device_type.get(device2) is None:
                        self.dic_device_type[device2] = tipo2
                        self.tipo_dispositivo(device2, tipo2)
                    self.separar_conexiones(device1, tipo1, x, device2, tipo2)

    def tipo_dispositivo(self, nombre, tipo):
        match(tipo):
            case "pc":
                device = D_pc(nombre, tipo)
                self.dic_device_objeto[nombre] = device
            case "sw": 
                device = D_sw(nombre, tipo)
                self.dic_device_objeto[nombre] = device
            case "r":
                self.lista_routers.append(nombre)
                device = D_r(nombre, tipo)
                self.dic_device_objeto[nombre] = device
            case "srv":
                device = D_serv(nombre, tipo)
                self.dic_device_objeto[nombre] = device


    def separar_conexiones(self, dev1, tipo1, x, dev2, tipo2):
        a,b,x,n_a,n_b = tipo1, tipo2, x, dev1, dev2
        if b.startswith("r"):
            a,b = b,a
            n_a, n_b = n_b, n_a
        elif b.startswith("sw") and a.startswith("pc"): 
            a,b = b,a
            n_a, n_b = n_b, n_a
        # Filtrado device-type
        if a.startswith("r") and b.startswith("r"):
            self.dic_conexiones['rr'][(n_a, n_b)] = x
        elif a.startswith("r") and b.startswith("sw"):
            self.dic_conexiones['rs'][(n_a, n_b)] = x
        elif a.startswith("r"):
            self.dic_conexiones['rd'][(n_a, n_b)] = x
        elif a.startswith("sw") and b.startswith("sw"):
            self.dic_conexiones['ss'][(n_a, n_b)] = x
        elif a.startswith("sw"):
            self.dic_conexiones['sd'][(n_a, n_b)] = x
        else:
            print("Dispositivo no reconocido")

    def read_pos(self, dic_device_objeto, path: str|None = None):
        if path is None:
            path = f"{self.ruta}/data/posiciones.csv"
        with open(path, mode='r', newline='', encoding='utf-8') as pos:
            reader = csv.reader(pos)
            
            for num_line, line in enumerate(reader, start=1):
                if len(line) != 3:
                    print(f"Error en la línea {num_line}")
                    continue
                dev, x, y = line
                if dic_device_objeto.get(dev) is not None:
                    device: D_pc|D_sw|D_r|D_serv = dic_device_objeto[dev]
                    device.x = int(x)
                    device.y = int(y)


class Operator_links:
    def __init__(self, dic_device_objeto, dic_conexiones):
        self.dic_device_objeto = dic_device_objeto
        self.dic_conexiones = dic_conexiones
        self.dic_edges = {}

        ##
        self.ip_1oct = 0
        ##
    def generar_ip_r_r(self, num:int):
        
        mask = '255.255.255.0'
        ip = f"{self.ip_1oct}.10.10.{num}"

        return (ip, mask)

    def get_links(self):
        self.validar_conexiones()
        return self.dic_edges

    def validar_conexiones(self):
        cables = {
            "c": "eStraightThrough",
            "cs": "eCrossOver", 
            "s": "serial"
        }
        for sub_dic in self.dic_conexiones:
            for (dev1, dev2), cable in self.dic_conexiones[sub_dic].items():
                object1: D_pc|D_sw|D_r|D_serv = self.dic_device_objeto[dev1]
                object2: D_pc|D_sw|D_r|D_serv = self.dic_device_objeto[dev2]

                interfaz1 = object1.add_link(cable, self.dic_device_objeto.get(dev2).id)
                interfaz2 = object2.add_link(cable, self.dic_device_objeto.get(dev1).id)
                
                if interfaz1 and interfaz2:
                    self.dic_edges[(dev1, dev2)] = (interfaz1, cables[cable] ,interfaz2)
                else:
                    print(f"Error al conectar {dev1} con {dev2} usando cable {cable}")
                if type(object1) is D_r and type(object2) is D_r:
                    self.ip_1oct +=10
                    red1 = self.generar_ip_r_r(1)
                    red2 = self.generar_ip_r_r(2)
                    object1.interfa_vlan[interfaz1] = [(1, red1[0], red1[1])] 
                    object2.interfa_vlan[interfaz2] = [(1, red2[0], red2[1])]
                    

class Operador_nets:
    def __init__(self, ruta, dic_device_objeto, dic_objeto_net):
        self.ruta = ruta
        self.dic_device_objeto = dic_device_objeto
        self.dic_objeto_net = dic_objeto_net

    def read_ips(self, path: str|None = None):
        if path is None:
            path = f"{self.ruta}/data/ips.csv"
        with open(path, mode='r', newline='', encoding='utf-8') as ips:
            reader = csv.reader(ips)
            
            for num_line, line in enumerate(reader, start=1):
                if len(line) != 3:
                    print(f"Error en la línea {num_line}")
                    continue
                dev, ip, mask = line
                if self.dic_device_objeto.get(dev) is not None:
                    net = IPv4Network(f"{ip}{mask}", strict=False)
                    dr,msk = net.network_address, net.netmask
                    gw = str(next(net.hosts()))
                    br = net.broadcast_address
                    device: D_pc|D_sw|D_r|D_serv = self.dic_device_objeto[dev]
                    device.ip = ip
                    device.mask = str(msk)
                    device.gw = gw
                    self.dic_objeto_net[dev] = (str(msk), str(dr), str(gw), str(br))


    def calcular_router_ramas(self, lista_routers, grafo_general):
        grafo = grafo_general
        dic_router_ramas ={}
        for router in lista_routers:
            dic_router_ramas[router] = {

            }
            for vecino in grafo.neighbors(router):
                tipo =  grafo.nodes[vecino]['type']
                if tipo != 'r':
                    interfaz_router = grafo[router][vecino]['data'][router]
                    objecto = grafo.nodes[vecino]['data']
                    dic_router_ramas[router][interfaz_router] = {
                        'sw': [],
                        'other_devices': [],
                        'vlans': {},
                        'num_vlans': 0
                    }
                    if tipo == 'sw':
                        dic_router_ramas[router][interfaz_router]['sw'] = [(vecino,objecto)]
                    else:
                        dic_router_ramas[router][interfaz_router]['other_devices'] = [(vecino,objecto)]
                    lista_visitados = [router, vecino]
                    lista_recorrer = deque([vecino])
                    while lista_recorrer:
                        u = lista_recorrer.popleft()
                        for v in grafo.neighbors(u):
                            if not v in lista_visitados and not v in lista_routers:
                                lista_recorrer.append(v)
                                lista_visitados.append(v)
                                tipo_aux =  grafo.nodes[v]['type']
                                objecto_aux = grafo.nodes[v]['data']
                                if tipo_aux == 'sw':
                                    dic_router_ramas[router][interfaz_router]['sw'].append((v,objecto_aux))
                                else:
                                    dic_router_ramas[router][interfaz_router]['other_devices'].append((v,objecto_aux))
                else: 
                    continue
        self.calcular_vlans(dic_router_ramas)
        self.calcular_vlans_sw(dic_router_ramas,grafo)

        return dic_router_ramas
    
    def calcular_vlans(self,dic_router_ramas):
        for router in dic_router_ramas:
            for interfaz in dic_router_ramas[router]: 
                dic_redes = {}
                for device, ob in itertools.chain(dic_router_ramas[router][interfaz]['sw'], dic_router_ramas[router][interfaz]['other_devices']):
                    objeto: D_sw = ob
                    atributes = self.dic_objeto_net.get(device)
                    if atributes == None:
                        continue
                    msk,dr,gw,_ = self.dic_objeto_net[device]
                    key = (dr,msk)
                    if dic_redes.get(key) is None:
                            dic_redes[key] = []
                            dic_router_ramas[router][interfaz]['num_vlans'] +=1
                            num_vlan  = dic_router_ramas[router][interfaz]['num_vlans']
                            dic_router_ramas[router][interfaz]['vlans'][(gw,msk)] = num_vlan
    
    def calcular_vlans_sw(self, dic_router_ramas, grafo: nx.Graph):
        dic_sw_ramas = {}
        for router in dic_router_ramas:
            for interfaz in dic_router_ramas[router]:
                router_objeto: D_r = self.dic_device_objeto[router]
                num_vlans = dic_router_ramas[router][interfaz]['num_vlans']
                router_objeto.interfa_vlan[interfaz] = [(vlan,net[0],net[1]) for net, vlan in dic_router_ramas[router][interfaz]['vlans'].items()]
                for sw, ob in dic_router_ramas[router][interfaz]['sw']:
                    objeto: D_sw = ob
                    for vecino in grafo.neighbors(sw):
                        tipo =  grafo.nodes[vecino]['type']
                        datos = grafo.get_edge_data(sw, vecino)
                        interfaz_aux = datos['data'][sw]
                        if tipo == 'sw' or tipo == 'r':
                            objeto.interfa_vlan[interfaz_aux] = {"modo": "trunk"}
                        else:
                            if self.dic_objeto_net.get(vecino)  is None:
                                continue
                            msk,_,gw,_ = self.dic_objeto_net[vecino]
                            key = (gw,msk)
                            vlan = dic_router_ramas[router][interfaz]['vlans'][key]
                            objeto.interfa_vlan[interfaz_aux] = {"modo": "access", "vlan": vlan}
                            objeto.num_vlans = num_vlans
                        

    def calcular_protocolos(self,dic,grafo):
        dic_datos = {}      
        for protocolo, lista in dic.items():
            for router in lista:
                objeto = self.dic_device_objeto[router]
                datos = objeto.get_nets(protocolo)
                dic_datos[datos[0]] = datos[1]
        self.calcular_routers_borde(dic_datos,grafo)
        return dic_datos

    def calcular_routers_borde(self, dic, grafo: nx.Graph):
        for router in dic:
            for vecino in grafo.neighbors(router):
                tipo =  grafo.nodes[vecino]['type']
                if tipo != 'r':
                    continue
                elif dic[vecino]['tipo'] != dic[router]['tipo']:
                    datos = grafo.get_edge_data(router, vecino)
                    interfaz_dev1 = datos['data'][router]
                    interfaz_dev2 = datos['data'][vecino]

                    dic[vecino]['rbp'] = interfaz_dev2
                    dic[router]['rbp'] = interfaz_dev1



        

