"""Image workflow and transactional IPv4 planning, independent of Qt."""
import copy
import csv
import io
import re
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Interface, IPv4Network
from pathlib import Path

from app import General_Core
from core_xml.main import GeneradorTopologia

UNUSABLE_NETWORKS = tuple(IPv4Network(value) for value in ('0.0.0.0/8', '127.0.0.0/8', '224.0.0.0/4', '240.0.0.0/4'))


def csv_rows(text):
    return [list(map(str.strip, row)) for row in csv.reader(io.StringIO(text.lstrip('\ufeff'))) if row and any(s.strip() for s in row)]


def validate_topology(connections, positions):
    devices, edges = {}, set()
    for number, row in enumerate(csv_rows(connections), 1):
        if len(row) != 3 or row[1] not in ('c', 'cs', 's'):
            raise ValueError(f'Conexión {number}: se esperan dispositivo:tipo,cable,dispositivo:tipo.')
        endpoints = []
        for endpoint in (row[0], row[2]):
            if endpoint == 'None:None':
                endpoints.append(None)
                continue
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,62}:(r|sw|pc|srv)', endpoint):
                raise ValueError(f'Conexión {number}: dispositivo o tipo inválido: {endpoint}.')
            name, kind = endpoint.split(':')
            if name in devices and devices[name] != kind:
                raise ValueError(f'Tipos contradictorios para {name}.')
            devices[name] = kind
            endpoints.append(name)
        a, b = endpoints
        if not a or a == b:
            raise ValueError(f'Conexión {number}: extremos inválidos.')
        if b:
            edge = frozenset((a, b))
            if edge in edges:
                raise ValueError(f'Enlace repetido: {a} / {b}.')
            edges.add(edge)
            if row[1] == 's' and (devices[a] != 'r' or devices[b] != 'r'):
                raise ValueError('Los enlaces seriales requieren dos routers.')
            if devices[a] in ('pc', 'srv') and devices[b] in ('pc', 'srv'):
                raise ValueError('El generador no admite enlaces directos entre equipos finales.')
    if not devices:
        raise ValueError('La imagen no produjo dispositivos.')
    seen = set()
    for row in csv_rows(positions):
        if len(row) != 3 or row[0] not in devices or row[0] in seen:
            raise ValueError('Posiciones incompletas, duplicadas o con dispositivos desconocidos.')
        try:
            x, y = int(row[1]), int(row[2])
            if min(x, y) < 0:
                raise ValueError()
        except ValueError:
            raise ValueError(f'Posición inválida para {row[0]}.') from None
        seen.add(row[0])
    if seen != set(devices):
        raise ValueError('Faltan posiciones para: ' + ', '.join(sorted(set(devices) - seen)))


@dataclass
class Branch:
    key: str
    router: str | None
    port: str | None
    switches: list
    hosts: list


def parse_ips(path):
    result = {}
    for number, row in enumerate(csv_rows(Path(path).read_text(encoding='utf-8-sig')), 1):
        if number == 1 and row[0].lower() in ('dispositivo', 'device', 'nombre'):
            continue
        if len(row) != 3:
            raise ValueError(f'IP, fila {number}: se esperan dispositivo,ip,máscara.')
        name, ip, mask = row
        if name in result:
            raise ValueError(f'IP repetida para el dispositivo {name}.')
        result[name] = (ip, mask)
    return result


class TopologySession:
    def __init__(self):
        self.base = None
        self.configured = None
        self.branches = []

    def load(self, connections, positions):
        validate_topology(Path(connections).read_text(encoding='utf-8-sig'), Path(positions).read_text(encoding='utf-8-sig'))
        core = General_Core()
        core.read_devices(str(connections))
        core.write_links_graph()
        expected = sum(bool(row[2] != 'None:None') for row in csv_rows(Path(connections).read_text(encoding='utf-8-sig')))
        if len(core.dic_edges) != expected:
            raise ValueError('La topología supera los puertos disponibles o contiene enlaces no compatibles.')
        core.send_devices_graph()
        core.send_links_graph()
        core.asignar_posiciones(str(positions), bandera=True)
        detected = core.calcular_ramas() or {}
        branches = []
        covered = set()
        for router, ports in detected.items():
            for port, data in ports.items():
                switches = [name for name, _ in data['sw']]
                hosts = [name for name, _ in data['other_devices']]
                branches.append(Branch(f'{router} / {port}', router, port, switches, hosts))
                covered.update(switches + hosts)
        # Preserve support for topologies without routers and isolated LANs.
        import networkx as nx
        remaining = set(core.dic_device_objeto) - covered - set(core.lista_routers)
        for index, component in enumerate(nx.connected_components(core.grafo_general.grafo.subgraph(remaining)), 1):
            switches = sorted(n for n in component if core.dic_device_type[n] == 'sw')
            hosts = sorted(component - set(switches))
            branches.append(Branch(f'LAN {index} (sin router)', None, None, switches, hosts))
        for device in core.dic_device_objeto.values():
            if hasattr(device, 'interfa_vlan'):
                device.interfa_vlan = {port: [] for port in device.interfa_device} if device.tipo == 'r' else {}
        self.base, self.configured, self.branches = core, None, branches

    def configure(self, plans, overrides=None, protocols=None):
        if self.base is None:
            raise ValueError('Primero analiza una imagen.')
        core = copy.deepcopy(self.base)
        overrides, protocols = overrides or {}, protocols or {}
        if set(plans) != {b.key for b in self.branches}:
            raise ValueError('Debes definir segmentos para todas las ramas.')
        members = {}
        for branch in self.branches:
            for name in branch.switches + branch.hosts:
                if name in members:
                    raise ValueError(f'{name} pertenece a varias ramas. Separa los dominios de capa 2 antes de configurar.')
                members[name] = branch.key
        known = set(members)
        for name in core.lista_routers:
            known.update(f'{name}@{port}' for port in core.dic_device_objeto[name].interfa_device)
        if set(overrides) - known:
            raise ValueError('Dispositivos o interfaces desconocidos: ' + ', '.join(sorted(set(overrides) - known)))
        fixed, used = {}, set()
        for name, (ip, mask) in overrides.items():
            try:
                addr = IPv4Interface(f'{ip}/{str(mask).lstrip("/")}')
            except ValueError:
                raise ValueError(f'{name}: IP o máscara inválida.') from None
            if addr.network.prefixlen > 30 or addr.ip in (addr.network.network_address, addr.network.broadcast_address) or addr.ip.is_multicast or addr.ip.is_unspecified or addr.ip.is_loopback:
                raise ValueError(f'{name}: la IP debe ser una dirección de host válida (/1 a /30).')
            if addr.ip in used:
                raise ValueError(f'IP duplicada: {addr.ip}.')
            used.add(addr.ip)
            fixed[name] = addr
        occupied, nets = [], {}

        def reserve(net, label):
            if net.prefixlen < 1 or net.prefixlen > 30 or any(net.overlaps(block) for block in UNUSABLE_NETWORKS):
                raise ValueError(f'{label}: utiliza una red IPv4 unicast válida entre /1 y /30, sin rangos reservados o de loopback.')
            for other, owner in occupied:
                if net.overlaps(other):
                    raise ValueError(f'Segmentos repetidos o superpuestos: {label} ({net}) y {owner} ({other}).')
            occupied.append((net, label))

        # Reserve manual and imported networks before choosing automatic networks.
        for branch in self.branches:
            values = plans[branch.key]
            if not 1 <= len(values) <= 128:
                raise ValueError(f'{branch.key}: selecciona entre 1 y 128 segmentos.')
            if len(values) > 1 and not branch.switches:
                raise ValueError(f'{branch.key}: varios segmentos requieren un switch.')
            networks = []
            for value in values:
                if value.strip():
                    try:
                        net = IPv4Network(value.strip(), strict=True)
                    except ValueError:
                        raise ValueError(f'{branch.key}: segmento inválido {value}; usa dirección de red/CIDR.') from None
                    reserve(net, branch.key)
                    networks.append(net)
                else:
                    networks.append(None)
            imported = {fixed[n].network for n in branch.switches + branch.hosts if n in fixed}
            router_key = f'{branch.router}@{branch.port}'
            if router_key in fixed:
                imported.add(fixed[router_key].network)
            for net in sorted(imported, key=lambda n: int(n.network_address)):
                if net in networks:
                    continue
                if None not in networks:
                    raise ValueError(f'{branch.key}: la red importada {net} no está entre los segmentos; aumenta la cantidad o edita los segmentos.')
                reserve(net, branch.key)
                networks[networks.index(None)] = net
            nets[branch.key] = networks
        # Router-to-router networks also participate in overlap validation.
        transit = []
        for (a, b), (pa, _, pb) in core.dic_edges.items():
            if core.dic_device_type[a] == core.dic_device_type[b] == 'r':
                keys = (f'{a}@{pa}', f'{b}@{pb}')
                imported = {fixed[k].network for k in keys if k in fixed}
                if len(imported) > 1:
                    raise ValueError(f'{a} / {b}: las interfaces del enlace deben compartir red y máscara.')
                net = next(iter(imported), None)
                if net:
                    reserve(net, f'{a} / {b}')
                transit.append((a, b, pa, pb, net))

        def automatic(prefix):
            for net in IPv4Network('10.0.0.0/8').subnets(new_prefix=prefix):
                if not any(net.overlaps(other) for other, _ in occupied):
                    reserve(net, 'automático')
                    return net
            raise ValueError('No hay espacio automático disponible en 10.0.0.0/8; introduce segmentos manualmente.')

        def allocate(net):
            for ip in net.hosts():
                if ip not in used:
                    used.add(ip)
                    return str(ip)
            raise ValueError(f'El segmento {net} no tiene suficientes IP disponibles.')

        assignments = {}
        for branch in self.branches:
            networks = [net or automatic(24) for net in nets[branch.key]]
            nets[branch.key] = networks
            router_key = f'{branch.router}@{branch.port}'
            if router_key in fixed and fixed[router_key].network != networks[0]:
                raise ValueError(f'{router_key}: la interfaz física debe usar el primer segmento (VLAN 1).')
            gateways = []
            for index, net in enumerate(networks):
                if branch.router:
                    gw = str(fixed[router_key].ip) if index == 0 and router_key in fixed else str(net.network_address + 1)
                    if not (index == 0 and router_key in fixed):
                        if IPv4Address(gw) in used:
                            raise ValueError(f'{branch.key}: {gw} está reservada para la puerta de enlace.')
                        used.add(IPv4Address(gw))
                    gateways.append(gw)
                else:
                    gateways.append('')
            for index, name in enumerate(branch.switches + branch.hosts):
                if name in fixed:
                    slot = networks.index(fixed[name].network)
                    if name in branch.switches and slot != 0:
                        raise ValueError(f'{name}: la administración del switch debe estar en el primer segmento (VLAN 1).')
                    ip = str(fixed[name].ip)
                else:
                    slot = 0 if name in branch.switches else (index - len(branch.switches)) % len(networks)
                    ip = allocate(networks[slot])
                net = networks[slot]
                device = core.dic_device_objeto[name]
                device.ip, device.mask, device.gw = ip, str(net.netmask), gateways[slot]
                assignments[name] = (slot + 1, net)
            if branch.router:
                core.dic_device_objeto[branch.router].interfa_vlan[branch.port] = [(i + 1, gateways[i], str(net.netmask)) for i, net in enumerate(networks)]
            for name in branch.switches:
                switch = core.dic_device_objeto[name]
                switch.num_vlans = len(networks)
                graph = core.grafo_general.grafo
                for neighbor in graph.neighbors(name):
                    port = graph[name][neighbor]['data'][name]
                    if core.dic_device_type[neighbor] in ('r', 'sw'):
                        switch.interfa_vlan[port] = {'modo': 'trunk'}
                    else:
                        switch.interfa_vlan[port] = {'modo': 'access', 'vlan': assignments[neighbor][0]}
        for a, b, pa, pb, net in transit:
            net = net or automatic(30)
            for name, port in ((a, pa), (b, pb)):
                key = f'{name}@{port}'
                ip = str(fixed[key].ip) if key in fixed else allocate(net)
                core.dic_device_objeto[name].interfa_vlan[port] = [(1, ip, str(net.netmask))]
        for name, protocol in protocols.items():
            if name not in core.lista_routers or protocol not in ('Sin protocolo', 'OSPF', 'RIP', 'EIGRP'):
                raise ValueError(f'Protocolo o router inválido: {name}.')
            if protocol != 'Sin protocolo':
                device = core.dic_device_objeto[name]
                if not any(device.interfa_vlan.values()):
                    raise ValueError(f'{name}: configura al menos una interfaz antes de elegir un protocolo.')
                _, data = device.get_nets(protocol)
                data['rbp'] = False
                core.dic_router_protocolo[name] = data
        self.configured = core
        return {key: [str(net) for net in values] for key, values in nets.items()}

    def generator(self, configured=False):
        core = self.configured if configured else self.base
        if core is None:
            raise ValueError('Analiza una imagen y valida la configuración si deseas incluirla.')
        data = {}
        names = {'pc': 'pcs', 'srv': 'srvs', 'r': 'routers', 'sw': 'switches'}
        for device in core.dic_device_objeto.values():
            data.setdefault(names[device.tipo], []).append(copy.deepcopy(device.get_atributes()))
        data['links'] = [{'from': a, 'to': b, 'from_port': pa, 'to_port': pb, 'tipo': cable} for (a, b), (pa, cable, pb) in core.dic_edges.items()]
        return GeneradorTopologia(data, copy.deepcopy(core.dic_router_protocolo), core.ruta)

    def export_markdown(self, folder, configured=False):
        generator = self.generator(configured)
        generator.crear_switches()
        generator.crear_routers()
        results = {}
        for kind, filename in (('sw', 'switches.md'), ('router', 'routers.md')):
            blocks = [f'# Configuración de {"switches" if kind == "sw" else "routers"}\n']
            for device in generator.dispositivos.values():
                if device['tipo'] != kind:
                    continue
                if kind == 'sw':
                    xml = generator.generar_interfaces_switch(device) + generator.generar_config_ip_switch(device)
                    vlans = '\n'.join(f'vlan {i}\n name VLAN{i:04d}\n exit' for i in range(2, device['vlans'] + 1))
                else:
                    xml = generator.generar_config_interfaces(device) + generator.generar_routing(device)
                    vlans = ''
                lines = '\n'.join(re.findall(r'<LINE>(.*?)</LINE>', xml))
                blocks.append(f'## {device["nombre"]}\n\n```ios\nenable\nconfigure terminal\nhostname {device["nombre"]}\n{vlans}\n{lines}\nend\nwrite memory\n```\n')
            results[filename] = '\n'.join(blocks)
        core = self.configured if configured else self.base
        rows = ['# PCs y servidores\n', '| Dispositivo | IP | Máscara | Puerta de enlace |', '| --- | --- | --- | --- |']
        for device in core.dic_device_objeto.values():
            if device.tipo in ('pc', 'srv'):
                rows.append(f'| {device.nombre} | {device.ip or "Sin configurar"} | {device.mask or "—"} | {device.gw or "—"} |')
        results = {'cisco.md': '# Configuración Cisco\n\n' + results['switches.md'] + '\n' + results['routers.md'],
                   'pcs.md': '\n'.join(rows) + '\n'}
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        for filename, text in results.items():
            (folder / filename).write_text(text, encoding='utf-8')
        return [folder / name for name in results]
