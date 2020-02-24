#!/usr/bin/env python3

import sys
import os
import json
import argparse
import itertools
import netaddr

import pynetbox

exporter_ports = {'linux': '9100', 'microsoft': '9182'}

def main(args):
    targets = []
    manufacturers = {'linux': [], 'microsoft': []}
    netbox = pynetbox.api(args.url, token=args.token)

    # Filter out devices without primary IP address as it is a requirement
    # to be polled by Prometheus
    devices = netbox.dcim.devices.filter(has_primary_ip=True)
    vm = netbox.virtualization.virtual_machines.filter(has_primary_ip=True)
    ips = netbox.ipam.ip_addresses.filter(**{'cf_%s' % args.custom_field: '{'})
    platforms = netbox.dcim.platforms.all()
    for platform in platforms:
        if str(platform.manufacturer).lower() == 'linux':
            manufacturers['linux'].append(platform.slug)
        elif str(platform.manufacturer).lower() == 'microsoft':
            manufacturers['microsoft'].append(platform.slug)

    for device in itertools.chain(devices, vm):
        if device.status.id == 1 and device.platform and device.platform.slug in manufacturers[args.exporter]:
            labels = {'__port__':  exporter_ports[args.exporter]}
            if getattr(device, 'name', None):
                labels['__meta_netbox_name'] = device.name
            else:
                labels['__meta_netbox_name'] = repr(device)
            if device.tenant:
                labels['__meta_netbox_tenant'] = device.tenant.slug
                if device.tenant.group:
                    labels['__meta_netbox_tenant_group'] = device.tenant.group.slug
            if getattr(device, 'cluster', None):
                labels['__meta_netbox_cluster'] = device.cluster.name
            if getattr(device, 'asset_tag', None):
                labels['__meta_netbox_asset_tag'] = device.asset_tag
            if getattr(device, 'device_role', None):
                labels['__meta_netbox_role'] = device.device_role.slug
            if getattr(device, 'device_type', None):
                labels['__meta_netbox_type'] = device.device_type.model
            if getattr(device, 'rack', None):
                labels['__meta_netbox_rack'] = device.rack.name
            if getattr(device, 'site', None):
                labels['__meta_netbox_pop'] = device.site.slug
            if getattr(device, 'serial', None):
                labels['__meta_netbox_serial'] = device.serial
            if getattr(device, 'parent_device', None):
                labels['__meta_netbox_parent'] = device.parent_device.name
            if getattr(device, 'address', None):
                labels['__meta_netbox_address'] = device.address
            if getattr(device, 'description', None):
                labels['__meta_netbox_description'] = device.description
            try:
                if device.custom_fields[args.custom_field]:
                    device_targets = json.loads(device.custom_fields[args.custom_field])
                else:
                    device_targets = [{'foo': 'bar'}]
            except ValueError:
                continue  # Ignore errors while decoding the target json FIXME: logging

            if not isinstance(device_targets, list):
                device_targets = [device_targets]

            for target in device_targets:
                target_labels = labels.copy()
                target_labels.update(target)
                if hasattr(device, 'primary_ip') and not device.primary_ip is None:
                    address = device.primary_ip
                #else:
                #    address = device
                targets.append({'targets': ['%s:%s' % (str(netaddr.IPNetwork(address.address).ip),
                                                       target_labels['__port__'])],
                                'labels': target_labels})

    temp_file = None
    if args.output == '-':
        output = sys.stdout
    else:
        temp_file = '{}.tmp'.format(args.output)
        output = open(temp_file, 'w')

    json.dump(targets, output, indent=4)
    output.write('\n')

    if temp_file:
        output.close()
        os.rename(temp_file, args.output)
    else:
        output.flush()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port', default=10000,
                        help='Default target port; Can be overridden using the __port__ label')
    parser.add_argument('-f', '--custom-field', default='prom_labels',
                        help='Netbox custom field to use to get the target labels')
    parser.add_argument('url', help='URL to Netbox')
    parser.add_argument('token', help='Authentication Token')
    parser.add_argument('output', help='Output file')
    parser.add_argument('exporter', help='Host OS: linux OR microsoft')

    args = parser.parse_args()

    main(args)
