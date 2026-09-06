import tempfile
import unittest
import zlib
import struct
from pathlib import Path
from xml.etree import ElementTree as ET

from core.workflow import TopologySession, parse_ips, validate_topology
from api_gemini.procesador import parse_response
from core_xml.generadores.xml2pkt import xor_data

CONNECTIONS = '''R1:r,c,SW1:sw
SW1:sw,c,PC1:pc
SW1:sw,c,PC2:pc
R1:r,s,R2:r
R2:r,c,SW2:sw
SW2:sw,c,PC3:pc
'''
POSITIONS = '\n'.join(f'{name},{100 + i * 100},100' for i, name in enumerate(['R1', 'SW1', 'PC1', 'PC2', 'R2', 'SW2', 'PC3']))


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)
        self.session = self.load(CONNECTIONS, POSITIONS)
        self.keys = [b.key for b in self.session.branches]
        self.plans = {key: [''] for key in self.keys}

    def load(self, connections, positions):
        c, p = self.path / 'conexiones.csv', self.path / 'pos.csv'
        c.write_text(connections, encoding='utf-8')
        p.write_text(positions, encoding='utf-8')
        session = TopologySession()
        session.load(c, p)
        return session

    def test_unconfigured_has_no_ip_vlan_or_protocol(self):
        generator = self.session.generator(False)
        self.assertFalse(generator.enrutamiento)
        self.assertTrue(all(not pc['ip'] for pc in generator.datos['pcs']))
        self.assertTrue(all(not data for r in generator.datos['routers'] for data in r['interfaces'].values()))
        self.assertTrue(all(not sw['puertos'] for sw in generator.datos['switches']))

    def test_automatic_and_per_router_protocols(self):
        nets = self.session.configure(self.plans, protocols={'R1': 'OSPF', 'R2': 'RIP'})
        self.assertNotEqual(nets[self.keys[0]], nets[self.keys[1]])
        core = self.session.configured
        self.assertEqual(core.dic_router_protocolo['R1']['tipo'], 'ospf')
        self.assertEqual(core.dic_router_protocolo['R2']['tipo'], 'ripv2')
        self.assertFalse(core.dic_router_protocolo['R2']['rbp'])
        self.assertIsNone(self.session.base.dic_device_objeto['PC1'].ip)

    def test_partial_protocol_assignment(self):
        self.session.configure(self.plans, protocols={'R1': 'EIGRP'})
        self.assertEqual(set(self.session.configured.dic_router_protocolo), {'R1'})

    def test_manual_imported_and_automatic_combined(self):
        self.plans[self.keys[0]] = ['192.168.10.0/24', '']
        resolved = self.session.configure(self.plans, {'PC2': ('192.168.20.40', '/24')})
        self.assertEqual(resolved[self.keys[0]], ['192.168.10.0/24', '192.168.20.0/24'])
        core = self.session.configured
        self.assertEqual(core.dic_device_objeto['PC2'].ip, '192.168.20.40')
        self.assertEqual(core.dic_device_objeto['PC2'].gw, '192.168.20.1')
        self.assertEqual(core.dic_device_objeto['PC1'].gw, '192.168.10.1')
        ports = core.dic_device_objeto['SW1'].interfa_vlan
        self.assertTrue(any(data.get('vlan') == 2 for data in ports.values()))

    def test_duplicate_or_overlapping_segments(self):
        for value in ('192.168.1.0/24', '192.168.1.128/25'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'superpuestos'):
                self.session.configure({self.keys[0]: ['192.168.1.0/24'], self.keys[1]: [value]})

    def test_non_network_cidr_rejected(self):
        self.plans[self.keys[0]] = ['192.168.1.20/24']
        with self.assertRaisesRegex(ValueError, 'segmento inválido'):
            self.session.configure(self.plans)

    def test_invalid_addresses(self):
        for ip, mask in [('300.1.1.1', '24'), ('192.168.1.0', '24'), ('192.168.1.255', '24'), ('192.168.1.2', '255.0.255.0'), ('127.0.0.2', '24'), ('224.0.0.2', '24')]:
            with self.subTest(ip=ip, mask=mask), self.assertRaises(ValueError):
                self.session.configure(self.plans, {'PC1': (ip, mask)})

    def test_duplicate_ips(self):
        with self.assertRaisesRegex(ValueError, 'duplicada'):
            self.session.configure(self.plans, {'PC1': ('192.168.1.2', '24'), 'PC2': ('192.168.1.2', '24')})

    def test_gateway_conflict(self):
        with self.assertRaisesRegex(ValueError, 'puerta de enlace'):
            self.session.configure(self.plans, {'PC1': ('192.168.1.1', '24')})

    def test_unknown_device(self):
        with self.assertRaisesRegex(ValueError, 'desconocidos'):
            self.session.configure(self.plans, {'PC999': ('192.168.1.2', '24')})

    def test_capacity(self):
        self.plans[self.keys[0]] = ['192.168.1.0/30']
        with self.assertRaisesRegex(ValueError, 'suficientes'):
            self.session.configure(self.plans)

    def test_out_of_segment_import(self):
        self.plans[self.keys[0]] = ['192.168.1.0/24']
        with self.assertRaisesRegex(ValueError, 'no está entre'):
            self.session.configure(self.plans, {'PC1': ('192.168.2.2', '24')})

    def test_imported_transit_and_gateway(self):
        core = self.session.base
        ports = core.grafo_general.grafo['R1']['R2']['data']
        overrides = {f'R1@{ports["R1"]}': ('172.16.0.1', '30'), f'R2@{ports["R2"]}': ('172.16.0.2', '30')}
        branch = self.session.branches[0]
        overrides[f'R1@{branch.port}'] = ('192.168.50.254', '24')
        self.session.configure(self.plans, overrides)
        self.assertEqual(self.session.configured.dic_device_objeto['PC1'].gw, '192.168.50.254')

    def test_transit_overlap_rejected(self):
        ports = self.session.base.grafo_general.grafo['R1']['R2']['data']
        self.plans[self.keys[0]] = ['192.168.1.0/24']
        with self.assertRaisesRegex(ValueError, 'superpuestos'):
            self.session.configure(self.plans, {f'R1@{ports["R1"]}': ('192.168.1.1', '30')})

    def test_transaction_failure_preserves_previous(self):
        self.session.configure(self.plans)
        previous = self.session.configured
        with self.assertRaises(ValueError):
            self.session.configure(self.plans, {'PC1': ('bad', '24')})
        self.assertIs(self.session.configured, previous)

    def test_reload_clears_configuration(self):
        self.session.configure(self.plans)
        self.session.load(self.path / 'conexiones.csv', self.path / 'pos.csv')
        self.assertIsNone(self.session.configured)

    def test_topology_without_routers(self):
        s = self.load('SW1:sw,c,PC1:pc\n', 'SW1,100,100\nPC1,200,100\n')
        s.configure({s.branches[0].key: ['']})
        self.assertEqual(s.configured.dic_device_objeto['PC1'].gw, '')

    def test_shared_layer_two_rejected_only_for_configuration(self):
        s = self.load('R1:r,c,SW1:sw\nR2:r,c,SW1:sw\n', 'R1,100,100\nR2,200,100\nSW1,300,100\n')
        s.generator(False)
        with self.assertRaisesRegex(ValueError, 'varias ramas'):
            s.configure({b.key: [''] for b in s.branches})

    def test_port_exhaustion(self):
        with self.assertRaisesRegex(ValueError, 'puertos'):
            self.load('R1:r,c,PC1:pc\nR2:r,c,PC1:pc\n', 'R1,100,100\nR2,200,100\nPC1,300,100\n')

    def test_two_markdown_files_and_configuration(self):
        self.plans[self.keys[0]] = ['', '']
        self.session.configure(self.plans, protocols={'R1': 'OSPF'})
        paths = self.session.export_markdown(self.path / 'export', True)
        self.assertEqual({p.name for p in paths}, {'cisco.md', 'pcs.md'})
        text = paths[0].read_text(encoding='utf-8')
        for command in ['router ospf 1', 'encapsulation dot1Q 2', 'switchport access vlan 2', 'no shutdown', 'vlan 2']:
            self.assertIn(command, text)
        self.assertNotIn('0.0.0.0 True', text)
        self.assertIn('PC1', paths[1].read_text(encoding='utf-8'))

    def test_pkt_roundtrip_and_fresh_generation(self):
        bare = self.path / 'bare.pkt'
        configured = self.path / 'configured.pkt'
        self.session.generator(False).generar(bare)
        self.session.configure(self.plans, protocols={'R1': 'OSPF'})
        self.session.generator(True).generar(configured)
        def decode(path):
            payload = path.read_bytes()
            payload = xor_data(payload, len(payload))
            xml = zlib.decompress(payload[4:])
            self.assertEqual(len(xml), struct.unpack('<I', payload[:4])[0])
            return ET.fromstring(xml), xml.decode('utf-8')
        bare_tree, bare_xml = decode(bare)
        _, configured_xml = decode(configured)
        self.assertNotIn('router ospf', bare_xml)
        self.assertIn('router ospf', configured_xml)
        self.assertNotIn('<LINE> ip address  </LINE>', bare_xml)
        self.assertTrue(all(not (e.text or '').strip() for e in bare_tree.iter('IP')))
        self.assertIn('PT-ROUTER-NM-1CGE', bare_xml)

    def test_ips_csv_header_bom_and_duplicate(self):
        path = self.path / 'ips.csv'
        path.write_text('\ufeffdispositivo,ip,mascara\nPC1,192.168.1.2,/24\n', encoding='utf-8')
        self.assertEqual(parse_ips(path), {'PC1': ('192.168.1.2', '/24')})
        path.write_text('PC1,192.168.1.2,24\nPC1,192.168.1.3,24\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            parse_ips(path)

    def test_api_parser_exact_files(self):
        response = f'### ARCHIVO: pos.csv\n```csv\n{POSITIONS}\n```\n### ARCHIVO: conexiones.csv\n```csv\n{CONNECTIONS}```'
        self.assertEqual(set(parse_response(response)), {'pos.csv', 'conexiones.csv'})
        for broken in [response.replace('pos.csv', '../bad.csv'), response + '\n### ARCHIVO: pos.csv\n```csv\nbad\n```', '```csv\nempty\n```', response.replace('PC1,300,100', 'UNKNOWN,300,100')]:
            with self.subTest(response=broken[:70]), self.assertRaises(ValueError):
                parse_response(broken)

    def test_malformed_and_unsafe_topology(self):
        for c, p in [('R1:r,c,R1:r', 'R1,100,100'), ('R1:r,c,SW1:sw\nR1:r,c,SW1:sw', 'R1,100,100\nSW1,200,100'), ('R1:r,c,SW<1:sw', ''), (CONNECTIONS, POSITIONS.replace('100,100', '-1,100', 1))]:
            with self.subTest(c=c[:30]), self.assertRaises(ValueError):
                validate_topology(c, p)


if __name__ == '__main__':
    unittest.main()
