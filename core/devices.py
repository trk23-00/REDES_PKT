from core.global_func import generar_save_ref_id as gen_id
from ipaddress import  IPv4Network

class Device_B:
    def __init__(self, nombre, tipo, id = None):
        self.nombre = nombre
        self.tipo = tipo 
        self.id = id
        self.generar_id()
        self.x = None
        self.y = None
    def generar_id(self):
        self.id = gen_id()
    def get_type(self):
        return self.tipo

class Device_A:
    def __init__(self, nombre, tipo, id=None, ip = None, mask = None):
        self.nombre = nombre
        self.tipo = tipo
        self.id = id
        self.ip = ip
        self.mask = mask
        self.gw = None
        self.x = None
        self.y = None
        self.generar_id()
    def generar_id(self):
        self.id = gen_id()
    def asignar_ip_msk(self, ip, mask):
        self.ip = ip
        self.mask = mask
    def get_type(self):
        return self.tipo
    def get_ip_msk(self):
        return self.ip, self.mask

class Device_pc(Device_A):
    def __init__(self, nombre, tipo, id=None, ip = None, mask = None):
        super().__init__(nombre, tipo, id, ip, mask)

        self.all_interfaces = {
            "fe":{
                "name": "FastEthernet",
                "libre": 1,
                "asignado": 0,
                "start": 0
            }
        }
        self.interfa_device = {}
    def add_link(self, cable, object_id):
        if self.all_interfaces["fe"]["libre"] > 0:
            if cable == "c" or cable=="cs": 
                interfaz = f"FastEthernet{self.all_interfaces['fe']['start']}"
                self.interfa_device[interfaz] = object_id
                self.all_interfaces["fe"]["libre"] -= 1
                self.all_interfaces["fe"]["asignado"] += 1
                self.all_interfaces["fe"]["start"] += 1
                return interfaz
        return False
    def get_atributes(self):
        return {
            "nombre": self.nombre,
            "tipo": self.tipo,
            "refId": self.id,
            "ip": self.ip,
            "mask": self.mask,
            "gw": self.gw,
            "interfaces": self.interfa_device,
            "x": self.x,
            "y": self.y
        }
    def get_type(self):
        return self.tipo

class Device_switch(Device_A):
    def __init__(self, nombre, tipo, id=None, ip = None, mask = None):
        super().__init__(nombre, tipo, id, ip, mask)
        self.all_interfaces = {
            "fe":{
                "name": "FastEthernet",
                "libre": 24,
                "asignado": 0,
                "start": 1
            },
            "ge":{
                "name": "GigabitEthernet",
                "libre": 2,
                "asignado": 0,
                "start": 1
            }
        }
        self.interfa_device = {}
        self.num_vlans = 0
        self.interfa_vlan = {}

    def add_link(self, cable, object_id):
        if cable == "c" or cable=="cs": 
            if self.all_interfaces["ge"]["libre"] > 0:
                num = self.all_interfaces["ge"]["start"]
                self.all_interfaces["ge"]["start"] += 1
                self.all_interfaces["ge"]["libre"] -= 1
                self.all_interfaces["ge"]["asignado"] += 1
                interfaz = f"GigabitEthernet0/{num}"
                self.interfa_device[interfaz] = object_id
                return interfaz
            if self.all_interfaces["fe"]["libre"] > 0:
                num = self.all_interfaces["fe"]["start"]
                self.all_interfaces["fe"]["start"] += 1
                self.all_interfaces["fe"]["libre"] -= 1
                self.all_interfaces["fe"]["asignado"] += 1
                interfaz = f"FastEthernet0/{num}"
                self.interfa_device[interfaz] = object_id
                return interfaz
        return False
    def get_atributes(self):
        return {
            "nombre": self.nombre,
            "x": self.x,
            "y": self.y,
            "tipo": self.tipo,
            "refId": self.id,
            "ip": self.ip,
            "mask": self.mask,
            "gw": self.gw,
            "vlans": self.num_vlans,
            "puertos": self.interfa_vlan
        }


class Device_router(Device_B):
    def __init__(self, nombre, tipo, id=None):
        super().__init__(nombre, tipo, id)
        self.vlan1 = False
        self.all_interfaces = {
            "all": 10,
            "start": 0,
            "asignado": 0
         }

        self.interfa_device = {}
        self.interfa_vlan = {}
    def add_link(self, cable, object_id):
        if self.all_interfaces['all'] > 0: 
            num = self.all_interfaces["start"]
            self.all_interfaces["start"] += 1
            self.all_interfaces["all"] -= 1
            self.all_interfaces["asignado"] += 1
            if cable == "c" or cable=="cs":
                interfaz = f"GigabitEthernet{num}/0"
                self.interfa_device[interfaz] = object_id
                return interfaz
            elif cable == "s":
                interfaz = f"Serial{num}/0"
                self.interfa_device[interfaz] = object_id
                return interfaz
        return False
    def get_atributes(self):
        return {
            "nombre": self.nombre,
            "tipo": self.tipo,
            "refId": self.id,
            "interfaces": self.interfa_vlan,
            "x": self.x,
            "y": self.y 
        }
    def get_nets(self, protocolo):
        datos = None
        match(protocolo):
            case 'RIP':
                datos = self.get_nets_rip()
            case 'EIGRP':
                datos = self.get_nets_eigrp()
            case 'OSPF':
                datos = self.get_nets_ospf()
        return datos

    def get_nets_rip(self):
        lista_nets = []
        dic = {
            "tipo": "ripv2",
            "rbp": False,

        }
        for lista in self.interfa_vlan.values():
            for red in lista:
                ip,mask = red[1], red[2]
                red = IPv4Network(f"{ip}/{mask}", strict=False)
                dr = str(red.network_address)
                lista_nets.append(dr)

        dic["network"] = lista_nets

        return self.nombre,dic
    
    def get_nets_eigrp(self):
        lista_nets = []
        dic = {
            "tipo": "eigrp",
            "rbp": False,
            "as": 100,
        }
        for lista in self.interfa_vlan.values():
            for red in lista:
                ip,mask = red[1], red[2]
                red = IPv4Network(f"{ip}/{mask}", strict=False)
                dr = str(red.network_address)
                lista_nets.append(dr)

        dic["network"] = lista_nets

        return self.nombre,dic
    
    def get_nets_ospf(self):
        dic_networks = []
        dic = {
            "tipo": "ospf", 
            "rbp": False,
            "process_id": 1,
            "network": []
        }
        for lista in self.interfa_vlan.values():
            for red in lista:
                ip,mask = red[1], red[2]
                red = IPv4Network(f"{ip}/{mask}", strict=False)
                wildmask= str(red.hostmask)
                dr = str(red.network_address)
                dic_networks.append({"red": dr, "wildcard":wildmask})
        
        dic["network"] = dic_networks
        return self.nombre,dic
    

class Device_serv(Device_pc):
    def __init__(self, nombre, tipo, id=None, ip = None, mask = None):
        super().__init__(nombre, tipo, id, ip, mask)

        self.all_interfaces = {
            "fe":{
                "name": "FastEthernet",
                "libre": 1,
                "asignado": 0,
                "start": 0
            }
        }
        self.interfa_device = {}
    def add_link(self, cable, object_id):
        if self.all_interfaces["fe"]["libre"] > 0:
            if cable == "c" or cable=="cs": 
                interfaz = f"FastEthernet{self.all_interfaces['fe']['start']}"
                self.interfa_device[interfaz] = object_id
                self.all_interfaces["fe"]["libre"] -= 1
                self.all_interfaces["fe"]["asignado"] += 1
                self.all_interfaces["fe"]["start"] += 1
                return interfaz
        return False
    def get_atributes(self):
        return {
            "nombre": self.nombre,
            "tipo": self.tipo,
            "refId": self.id,
            "ip": self.ip,
            "mask": self.mask,
            "gw": self.gw,
            "interfaces": self.interfa_device,
            "x": self.x,
            "y": self.y
        }
    def get_type(self):
        return self.tipo
