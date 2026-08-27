from core.global_func import generar_save_ref_id as gen_id
from core_xml.main import GeneradorTopologia as Gen_xml
import time
import os
import pprint
## OPERADORES CLASES
from core.operadores import (
    Operator_reader as O_reader,
    Operator_links as O_links,
    Operador_nets as O_nets
)
## GRAFO CLASES
from core.grafo import Grafo_red

class General_Core:
    def __init__(self):
        ruta_script = os.path.dirname(os.path.abspath(__file__)).replace('\\','/')
        self.ruta = ruta_script
        ## General Corej
        self.dic_device_type = {}
        self.dic_conexiones = {}
        self.dic_device_objeto = {}
        self.dic_edges = {}
        self.lista_routers = []
        ## Special Core
        self.dic_general = {}
        self.dic_objeto_net = {}
        ## clases especales (constantes)
        self.grafo_general = Grafo_red()
        self.cal_redes = O_nets(self.ruta, self.dic_device_objeto, self.dic_objeto_net)
        self.generador_topologia: Gen_xml|None = None
        ## PARA XML - protocolo
        self.dic_protocolo_aux = {}
        self.dic_router_protocolo = {}

    def read_devices(self,path):
        operator = O_reader(self.ruta)
        dic_device_type, dic_device_objeto, dic_conexiones = operator.get_core(path)

        self.dic_device_type.clear()
        self.dic_device_type.update(dic_device_type)

        self.dic_device_objeto.clear()
        self.dic_device_objeto.update(dic_device_objeto)

        self.dic_conexiones.clear()
        self.dic_conexiones.update(dic_conexiones)

        self.lista_routers = operator.lista_routers  

    def write_links_graph(self):
        operator = O_links(self.dic_device_objeto, self.dic_conexiones)
        self.dic_edges = operator.get_links()

    def send_devices_graph(self):
        if self.dic_device_objeto:
            devices = self.dic_device_objeto.items()
            self.grafo_general.add_all_nodes(devices)
    def send_links_graph(self):
        if self.dic_edges:
            edges = self.dic_edges.items()
            self.grafo_general.add_all_edges(edges)
    def put_ips_devices(self, path: str|None = None):
        self.cal_redes.read_ips(path)
    def asignar_posiciones(self, path: str|None = None, bandera=False):
        if not bandera:
            self.grafo_general.asignar_posiciones()
        else:
            operator = O_reader(self.ruta)
            operator.read_pos(self.dic_device_objeto, path)
            

    
    def calcular_ramas(self):
        if self.lista_routers:
            return self.cal_redes.calcular_router_ramas(self.lista_routers, self.grafo_general.grafo)
        else: 
            print("No se pudo realizar inter-vlans; no existe ROUTERS en la topologia")
            return None


    def aplicar_protocolos(self):
        self.calcular_ramas()
        # pprint.pprint(self.dic_protocolo_aux)
        self.dic_router_protocolo = self.cal_redes.calcular_protocolos(self.dic_protocolo_aux, self.grafo_general.grafo)
        # pprint.pprint(self.dic_router_protocolo)
        
    def send_devices_attributes_xml(self):
        self.aplicar_protocolos()
        dic_all_atributes = {
            "pds": [
                {"nombre": "PD1", "x": 0, "y": 0},
                {"nombre": "PD2", "x": 50, "y": 0}
            ]
        }

        lista_links = []
        for objeto in self.dic_device_objeto.values():
            device_type = objeto.get_type()
            match (device_type):
                case 'pc': device_type = "pcs"
                case 'sw': device_type = "switches"
                case 'r': device_type = "routers"
                case 'srv': device_type = "srvs"

            if not device_type in dic_all_atributes:    
                dic_all_atributes[device_type] = []
            dic_all_atributes[device_type].append(objeto.get_atributes())
        for devices, info in self.dic_edges.items():
            d1,d2 = devices
            i1,cable, i2 = info
            lista_links.append({"from": d1, "to": d2, "from_port": i1, "to_port": i2, "tipo": cable})
        dic_all_atributes["links"] = lista_links
        if self.generador_topologia == None:
            self.generador_topologia = Gen_xml(dic_all_atributes,self.dic_router_protocolo,self.ruta)
        pprint.pprint(dic_all_atributes)
        self.generador_topologia.generar()
        return dic_all_atributes
##
"""inicio = time.time()
calA = General_Core()
calA.read_devices()
calA.write_links_graph()
calA.send_devices_graph()
calA.send_links_graph()
grafo_g = calA.grafo_general"""###
"""print("NODES")
for i in grafo_g.grafo.nodes(data=True):
    print(i)

print("EDGES")
for i in grafo_g.grafo.edges:
    print(i)
"""
print("####################")

"""for i in calA.dic_edges.items():
    print(i)
for i in grafo_g.grafo.edges(data=True):
    print(i)"""

##calA.asignar_posiciones()
"""

print("####################")
calA.put_ips_devices()

calA.asignar_posiciones(True)
a = calA.calcular_ramas()
protocolos = {
    "OSPF": ["R1", "R2", "R3", "R4", "R8"]
}
calA.aplicar_protocolos(protocolos)
b = calA.send_devices_attributes_xml()

pprint.pprint(b)"""

####
"""calA.read_devices()
calA.send_devices()
calA.validar_conexiones() 
print("Nodes")
for i in calA.grafo_general.grafo.nodes():
    print(i)

print("EDGES")
for i in calA.dic_edges.items():
    print(i)


for objeto in calA.dic_device_objeto.values():
    print(objeto.id)"""