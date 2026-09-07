"""Sesión de topología, validación por etapas y exportación, sin dependencia de Qt."""
import copy
import csv
import io
import re
from dataclasses import dataclass
from ipaddress import IPv4Interface, IPv4Network
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


@dataclass
class ConfigurationInput:
    """Valores interpretados del formulario; no contiene copias del core."""
    networks: dict
    addresses: dict
    protocols: dict


@dataclass
class ConfigurationChanges:
    """Asignaciones pendientes. Solo se aplican tras superar la validación final."""
    networks: dict
    addresses: dict
    router_interfaces: dict
    switch_ports: dict
    switch_vlans: dict
    protocols: dict


class AddressPool:
    """Reservas usadas exclusivamente durante la validación final."""
    def __init__(self, addresses):
        self.networks = []
        self.used_ips = set()
        for address in addresses.values():
            if address.ip in self.used_ips:
                raise ValueError(f'IP duplicada: {address.ip}.')
            self.used_ips.add(address.ip)

    def reserve(self, network, owner):
        for previous, previous_owner in self.networks:
            if network.overlaps(previous):
                raise ValueError(f'Segmentos repetidos o superpuestos: {owner} ({network}) y {previous_owner} ({previous}).')
        self.networks.append((network, owner))

    def automatic_network(self, prefix):
        for network in IPv4Network('10.0.0.0/8').subnets(new_prefix=prefix):
            if not any(network.overlaps(previous) for previous, _ in self.networks):
                self.reserve(network, 'automático')
                return network
        raise ValueError('No hay espacio automático disponible en 10.0.0.0/8; introduce segmentos manualmente.')

    def allocate_ip(self, network):
        for address in network.hosts():
            if address not in self.used_ips:
                self.used_ips.add(address)
                return str(address)
        raise ValueError(f'El segmento {network} no tiene suficientes IP disponibles.')

    def reserve_gateway(self, network, owner):
        address = network.network_address + 1
        if address in self.used_ips:
            raise ValueError(f'{owner}: {address} está reservada para la puerta de enlace.')
        self.used_ips.add(address)
        return str(address)


class TopologySession:
    def __init__(self):
        self.core = General_Core()
        self.is_loaded = False
        self.has_configuration = False
        self.branches = []

    # Carga y estado de la sesión

    def load(self, connections, positions):
        connection_text = Path(connections).read_text(encoding='utf-8-sig')
        position_text = Path(positions).read_text(encoding='utf-8-sig')
        validate_topology(connection_text, position_text)
        self._reset_topology()
        self.core.read_devices(str(connections))
        self.core.write_links_graph()
        expected = sum(row[2] != 'None:None' for row in csv_rows(connection_text))
        if len(self.core.dic_edges) != expected:
            raise ValueError('La topología supera los puertos disponibles o contiene enlaces no compatibles.')
        self.core.send_devices_graph()
        self.core.send_links_graph()
        self.core.asignar_posiciones(str(positions), bandera=True)
        self._detect_branches()
        self._clear_configuration()
        self.is_loaded = True

    def _reset_topology(self):
        self.is_loaded = False
        self.has_configuration = False
        self.branches.clear()
        self.core.grafo_general.grafo.clear()
        self.core.grafo_general.grafo_lleno = False
        self.core.dic_device_type.clear()
        self.core.dic_device_objeto.clear()
        self.core.dic_conexiones.clear()
        self.core.dic_edges.clear()
        self.core.lista_routers.clear()
        self.core.dic_general.clear()
        self._clear_configuration()

    def _clear_configuration(self):
        self.core.dic_objeto_net.clear()
        self.core.dic_protocolo_aux.clear()
        self.core.dic_router_protocolo.clear()
        self.core.generador_topologia = None
        for device in self.core.dic_device_objeto.values():
            if device.tipo == 'r':
                device.interfa_vlan = {port: [] for port in device.interfa_device}
            else:
                device.ip = device.mask = device.gw = None
                if device.tipo == 'sw':
                    device.interfa_vlan = {}
                    device.num_vlans = 0

    def invalidate_configuration(self):
        """Editar invalida la salida configurada; no borra la última asignación."""
        self.has_configuration = False

    def _require_topology(self):
        if not self.is_loaded:
            raise ValueError('Primero analiza una imagen.')

    def _detect_branches(self):
        import networkx as nx
        covered = set()
        for router, ports in (self.core.calcular_ramas() or {}).items():
            for port, data in ports.items():
                switches = [name for name, _ in data['sw']]
                hosts = [name for name, _ in data['other_devices']]
                self.branches.append(Branch(f'{router} / {port}', router, port, switches, hosts))
                covered.update(switches + hosts)
        remaining = set(self.core.dic_device_objeto) - covered - set(self.core.lista_routers)
        for index, component in enumerate(nx.connected_components(self.core.grafo_general.grafo.subgraph(remaining)), 1):
            switches = sorted(name for name in component if self.core.dic_device_type[name] == 'sw')
            self.branches.append(Branch(f'LAN {index} (sin router)', None, None, switches, sorted(component - set(switches))))

    def address_targets(self):
        for name, device in self.core.dic_device_objeto.items():
            if device.tipo == 'r':
                yield from (f'{name}@{port}' for port in device.interfa_device)
            else:
                yield name

    # Comprobaciones comunes: edición y confirmación final

    def validate_address_targets(self, overrides):
        unknown = set(overrides) - set(self.address_targets())
        if unknown:
            raise ValueError('Dispositivos o interfaces desconocidos: ' + ', '.join(sorted(unknown)))

    @staticmethod
    def _validate_network(network, owner):
        if not 1 <= network.prefixlen <= 30 or any(network.overlaps(block) for block in UNUSABLE_NETWORKS):
            raise ValueError(f'{owner}: utiliza una red IPv4 unicast válida entre /1 y /30, sin rangos reservados o de loopback.')

    def _parse_addresses(self, overrides, complete):
        self.validate_address_targets(overrides)
        addresses = {}
        for name, (ip, mask) in overrides.items():
            ip, mask = ip.strip(), str(mask).strip()
            if not ip and not mask:
                continue
            if not ip or not mask:
                if complete:
                    raise ValueError(f'{name}: introduce IP y máscara juntas o deja ambas vacías.')
                continue
            try:
                address = IPv4Interface(f'{ip}/{mask.lstrip("/")}')
            except ValueError:
                raise ValueError(f'{name}: IP o máscara inválida.') from None
            if address.ip in (address.network.network_address, address.network.broadcast_address):
                raise ValueError(f'{name}: la IP debe ser una dirección de host válida (/1 a /30).')
            self._validate_network(address.network, name)
            addresses[name] = address
        return addresses

    def _parse_segment(self, value, owner):
        if not value.strip():
            return None
        try:
            network = IPv4Network(value.strip(), strict=True)
        except ValueError:
            raise ValueError(f'{owner}: segmento inválido {value}; usa dirección de red/CIDR.') from None
        self._validate_network(network, owner)
        return network

    @staticmethod
    def _validate_segment_count(branch, count):
        if not 1 <= count <= 128:
            raise ValueError(f'{branch.key}: selecciona entre 1 y 128 segmentos.')
        if count > 1 and not branch.switches:
            raise ValueError(f'{branch.key}: varios segmentos requieren un switch.')

    def _infer_branch_networks(self, branch, values, addresses):
        self._validate_segment_count(branch, len(values))
        networks = [self._parse_segment(value, branch.key) for value in values]
        router_target = f'{branch.router}@{branch.port}'
        targets = branch.switches + branch.hosts + [router_target]
        provided = {addresses[name].network for name in targets if name in addresses}
        for network in sorted(provided, key=lambda value: (int(value.network_address), value.prefixlen)):
            if network not in networks:
                if None in networks:
                    networks[networks.index(None)] = network
                else:
                    networks.append(network)
        self._validate_segment_count(branch, len(networks))
        management = {addresses[name].network for name in branch.switches + [router_target] if name in addresses}
        if len(management) > 1:
            raise ValueError(f'{branch.key}: las IP de administración de switches y la interfaz física del router deben compartir la red de VLAN 1.')
        if management:
            primary = next(iter(management))
            networks.remove(primary)
            networks.insert(0, primary)
        return networks

    def _validate_protocol_choices(self, protocols):
        for name, protocol in protocols.items():
            if name not in self.core.lista_routers or protocol not in ('Sin protocolo', 'OSPF', 'RIP', 'EIGRP'):
                raise ValueError(f'Protocolo o router inválido: {name}.')
        selected = set(protocols.values()) - {'Sin protocolo'}
        if len(selected) > 2:
            raise ValueError('Solo se permiten dos protocolos distintos por topología. Sin protocolo no cuenta para este límite.')

    def _read_configuration(self, plans, overrides, protocols, *, complete):
        self._require_topology()
        if set(plans) != {branch.key for branch in self.branches}:
            raise ValueError('Debes definir segmentos para todas las ramas.')
        addresses = self._parse_addresses(overrides, complete)
        self._validate_protocol_choices(protocols)
        networks = {branch.key: self._infer_branch_networks(branch, plans[branch.key], addresses) for branch in self.branches}
        return ConfigurationInput(networks, addresses, protocols)

    @staticmethod
    def _segment_text(networks):
        return {key: [str(network) if network else '' for network in values] for key, values in networks.items()}

    # Validación durante la edición: sin reservas ni asignación de IP

    def validate_edit(self, plans, overrides=None, protocols=None):
        values = self._read_configuration(plans, overrides or {}, protocols or {}, complete=False)
        return self._segment_text(values.networks)

    # Validación final: comprueba el conjunto y prepara cambios sin tocar el core

    def _validate_branch_membership(self):
        visited = set()
        for branch in self.branches:
            for name in branch.switches + branch.hosts:
                if name in visited:
                    raise ValueError(f'{name} pertenece a varias ramas. Separa los dominios de capa 2 antes de configurar.')
                visited.add(name)

    def _transit_links(self):
        for (first, second), (first_port, _, second_port) in self.core.dic_edges.items():
            if self.core.dic_device_type[first] == self.core.dic_device_type[second] == 'r':
                yield first, second, first_port, second_port

    def _reserve_networks(self, values, pool):
        for owner, networks in values.networks.items():
            for network in networks:
                if network is not None:
                    pool.reserve(network, owner)
        transit = {}
        for first, second, first_port, second_port in self._transit_links():
            targets = (f'{first}@{first_port}', f'{second}@{second_port}')
            provided = {values.addresses[name].network for name in targets if name in values.addresses}
            if len(provided) > 1:
                raise ValueError(f'{first} / {second}: las interfaces del enlace deben compartir red y máscara.')
            network = next(iter(provided), None)
            if network:
                pool.reserve(network, f'{first} / {second}')
            transit[(first, second)] = network
        return transit

    def _plan_branch(self, branch, values, changes, pool):
        networks = changes.networks[branch.key]
        router_target = f'{branch.router}@{branch.port}'
        gateways = []
        for index, network in enumerate(networks):
            if not branch.router:
                gateways.append('')
            elif index == 0 and router_target in values.addresses:
                gateways.append(str(values.addresses[router_target].ip))
            else:
                gateways.append(pool.reserve_gateway(network, branch.key))
        access_vlans = {}
        for index, name in enumerate(branch.switches + branch.hosts):
            if name in values.addresses:
                vlan_index = networks.index(values.addresses[name].network)
                ip = str(values.addresses[name].ip)
            else:
                vlan_index = 0 if name in branch.switches else (index - len(branch.switches)) % len(networks)
                ip = pool.allocate_ip(networks[vlan_index])
            network = networks[vlan_index]
            changes.addresses[name] = (ip, str(network.netmask), gateways[vlan_index])
            access_vlans[name] = vlan_index + 1
        if branch.router:
            changes.router_interfaces[branch.router][branch.port] = [
                (index + 1, gateways[index], str(network.netmask)) for index, network in enumerate(networks)]
        for name in branch.switches:
            changes.switch_vlans[name] = len(networks)
            changes.switch_ports[name] = {}
            for neighbor in self.core.grafo_general.grafo.neighbors(name):
                port = self.core.grafo_general.grafo[name][neighbor]['data'][name]
                changes.switch_ports[name][port] = (
                    {'modo': 'trunk'} if self.core.dic_device_type[neighbor] in ('r', 'sw')
                    else {'modo': 'access', 'vlan': access_vlans[neighbor]})

    def _plan_transit(self, values, changes, transit, pool):
        for first, second, first_port, second_port in self._transit_links():
            network = transit[(first, second)] or pool.automatic_network(30)
            for name, port in ((first, first_port), (second, second_port)):
                target = f'{name}@{port}'
                ip = str(values.addresses[target].ip) if target in values.addresses else pool.allocate_ip(network)
                changes.router_interfaces[name][port] = [(1, ip, str(network.netmask))]

    def validate_configuration(self, plans, overrides=None, protocols=None):
        values = self._read_configuration(plans, overrides or {}, protocols or {}, complete=True)
        self._validate_branch_membership()
        pool = AddressPool(values.addresses)
        transit = self._reserve_networks(values, pool)
        # Los espacios automáticos se completan después de reservar TODAS las
        # redes proporcionadas, incluidos los enlaces entre routers.
        for networks in values.networks.values():
            for index, network in enumerate(networks):
                if network is None:
                    networks[index] = pool.automatic_network(24)
        changes = ConfigurationChanges(
            networks=values.networks, addresses={},
            router_interfaces={name: {port: [] for port in self.core.dic_device_objeto[name].interfa_device} for name in self.core.lista_routers},
            switch_ports={}, switch_vlans={}, protocols=values.protocols)
        for branch in self.branches:
            self._plan_branch(branch, values, changes, pool)
        self._plan_transit(values, changes, transit, pool)
        for name, protocol in values.protocols.items():
            if protocol != 'Sin protocolo' and not any(changes.router_interfaces[name].values()):
                raise ValueError(f'{name}: configura al menos una interfaz antes de elegir un protocolo.')
        return changes

    def configure(self, plans, overrides=None, protocols=None):
        changes = self.validate_configuration(plans, overrides, protocols)
        self._apply_configuration(changes)
        self.has_configuration = True
        return self._segment_text(changes.networks)

    def _apply_configuration(self, changes):
        self._clear_configuration()
        for name, (ip, mask, gateway) in changes.addresses.items():
            self.core.dic_device_objeto[name].ip = ip
            self.core.dic_device_objeto[name].mask = mask
            self.core.dic_device_objeto[name].gw = gateway
            network = IPv4Network(f'{ip}/{mask}', strict=False)
            self.core.dic_objeto_net[name] = (mask, str(network.network_address), gateway, str(network.broadcast_address))
        for name, interfaces in changes.router_interfaces.items():
            self.core.dic_device_objeto[name].interfa_vlan = interfaces
        for name, ports in changes.switch_ports.items():
            self.core.dic_device_objeto[name].interfa_vlan = ports
            self.core.dic_device_objeto[name].num_vlans = changes.switch_vlans[name]
        for name, protocol in changes.protocols.items():
            if protocol != 'Sin protocolo':
                self.core.dic_protocolo_aux.setdefault(protocol, []).append(name)
                _, routing = self.core.dic_device_objeto[name].get_nets(protocol)
                self.core.dic_router_protocolo[name] = routing
        # La vista excluye routers sin protocolo: no representan fronteras
        # entre protocolos y el detector existente espera vecinos configurados.
        self.core.cal_redes.calcular_routers_borde(
            self.core.dic_router_protocolo,
            self.core.grafo_general.grafo.subgraph(self.core.dic_router_protocolo))

    # Salidas: el modo sin configuración se representa al serializar,
    # sin mantener una segunda topología ni modificar self.core.

    def generator(self, configured=False):
        self._require_topology()
        if configured and not self.has_configuration:
            raise ValueError('Valida la configuración antes de incluirla en la salida.')
        data = {}
        groups = {'pc': 'pcs', 'srv': 'srvs', 'r': 'routers', 'sw': 'switches'}
        for device in self.core.dic_device_objeto.values():
            attributes = device.get_atributes()
            if not configured:
                if device.tipo == 'r':
                    attributes['interfaces'] = {port: [] for port in device.interfa_device}
                else:
                    attributes.update(ip=None, mask=None, gw=None)
                    if device.tipo == 'sw':
                        attributes.update(vlans=0, puertos={})
            data.setdefault(groups[device.tipo], []).append(attributes)
        data['links'] = [{'from': first, 'to': second, 'from_port': first_port, 'to_port': second_port, 'tipo': cable}
                         for (first, second), (first_port, cable, second_port) in self.core.dic_edges.items()]
        # Única copia de salida: el generador XML modifica diccionarios anidados.
        # Se aísla el documento, nunca General_Core ni su grafo/dispositivos.
        data, routing = copy.deepcopy((data, self.core.dic_router_protocolo if configured else {}))
        return GeneradorTopologia(data, routing, self.core.ruta)

    @staticmethod
    def _cisco_markdown(generator, kind):
        blocks = [f'# Configuración de {"switches" if kind == "sw" else "routers"}\n']
        for device in generator.dispositivos.values():
            if device['tipo'] != kind:
                continue
            if kind == 'sw':
                xml = generator.generar_interfaces_switch(device) + generator.generar_config_ip_switch(device)
                vlans = '\n'.join(f'vlan {index}\n name VLAN{index:04d}\n exit' for index in range(2, device['vlans'] + 1))
            else:
                xml = generator.generar_config_interfaces(device) + generator.generar_routing(device)
                border_port = generator.enrutamiento.get(device['nombre'], {}).get('rbp')
                if border_port:
                    xml = f'<LINE>ip route 0.0.0.0 0.0.0.0 {border_port}</LINE>\n' + xml
                vlans = ''
            commands = '\n'.join(re.findall(r'<LINE>(.*?)</LINE>', xml))
            blocks.append(f'## {device["nombre"]}\n\n```ios\nenable\nconfigure terminal\nhostname {device["nombre"]}\n{vlans}\n{commands}\nend\nwrite memory\n```\n')
        return '\n'.join(blocks)

    def _pcs_markdown(self, configured):
        rows = ['# PCs y servidores\n', '| Dispositivo | IP | Máscara | Puerta de enlace |', '| --- | --- | --- | --- |']
        for device in self.core.dic_device_objeto.values():
            if device.tipo in ('pc', 'srv'):
                ip, mask, gateway = (device.ip, device.mask, device.gw) if configured else (None, None, None)
                rows.append(f'| {device.nombre} | {ip or "Sin configurar"} | {mask or "—"} | {gateway or "—"} |')
        return '\n'.join(rows) + '\n'

    def export_markdown(self, folder, configured=False):
        generator = self.generator(configured)
        generator.crear_switches()
        generator.crear_routers()
        documents = {
            'cisco.md': '# Configuración Cisco\n\n' + self._cisco_markdown(generator, 'sw') + '\n' + self._cisco_markdown(generator, 'router'),
            'pcs.md': self._pcs_markdown(configured)}
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        for filename, text in documents.items():
            (folder / filename).write_text(text, encoding='utf-8')
        return [folder / name for name in documents]
