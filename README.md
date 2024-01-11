# DEPRECATED: Use Home Assistant's built-in (OPower Integration)[https://www.home-assistant.io/integrations/opower/], it now supports Portland General Electric, and their implementation is rock-solid.

<!-- [![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs) -->

![Version](https://img.shields.io/github/v/release/ejpenney/ha-portlandgeneral)
![Downloads](https://img.shields.io/github/downloads/ejpenney/ha-portlandgeneral/total)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![StandWithUkraine](https://raw.githubusercontent.com/vshymanskyy/StandWithUkraine/main/badges/StandWithUkraine.svg)](https://github.com/vshymanskyy/StandWithUkraine/blob/main/docs/README.md)
[![Coverage Status](https://coveralls.io/repos/github/ejpenney/ha-portlandgeneral/badge.svg?branch=master)](https://coveralls.io/github/ejpenney/ha-portlandgeneral?branch=master)

# Portland General Electric for Home Assistant

## Installation

### HACS - (RECOMMENDED)

0. Have [HACS](https://github.com/custom-components/hacs) installed, this will allow you to easily update
1. Add `https://github.com/ejpenney/ha-portlandgeneral` as a [custom repository](https://custom-components.github.io/hacs/usage/settings/#add-custom-repositories) as Type: Integration
2. Click install under "HA Portland General Electric"
3. Restart Home Assistant.

### Manual

Copy `custom_components/portland_general_electric` into your Home Assistant `config` directory.

### Post installation steps

- Restart HA
- Browse to your Home Assistant instance
- In the sidebar click on Settings.
- From the configuration menu select: Devices & Services.
- In the bottom right, click on the Add Integration button.
- From the list, search and select “HA Portland General Electric”.
- Follow the instruction on screen to complete the set up.

## What is this?

Based heavily on the work of [portlandgeneral-api](https://github.com/piekstra/portlandgeneral-api) this component is meant to add energy usage entities to Home Assistant for [Portland General Electric](https://portlandgeneral.com/) customers who don't have smart meters, or [other means of live measurement](https://www.home-assistant.io/blog/2021/08/04/home-energy-management/). The hope is to use these in the [Energy Dashboard](https://www.home-assistant.io/dashboards/energy)

## Support

Hey dude! Help me out for a couple of :beers: or a :coffee:!

[![coffee](https://www.buymeacoffee.com/assets/img/custom_images/black_img.png)](https://www.buymeacoffee.com/ejpenney)

## Known limitations

### Hourly Sensor

It does not appear PGE updates this data until 24-48 hours after the fact, so it appears useless for "live" monitoring of usage. I've left it turned on while I continue to experiment.

### Daily Sensor

PGE's daily sensor suffers from similar issues, the number doesn't finalize until around midnight therefore we cannot get "today's" usage. Instead we're using the `utility_cost_daily()` call, this data is mostly accurate. It appears to be updated 2-3 times per day. This has the added bonus of reporting "Provided Cost".

### Cost Sensor

Assumes PGE tiers up to 1,000 KWH at one price and the second price for beyond. This is typically true. Contains an attribute with a calculated total consumption this billing period. Not 100% accurate but should be close.

### WIP Disclaimer

This integration is still WIP, I'm running it locally on a test instance of HASS, it is NOT working at the moment, as in it doesn't do anything particularly useful. I'm still working out the best way to leverage the intermittently updated data, while simultaneously learning about writing custom components.

## Development

Developed using VSCode, testing in Docker. UnitTests have not yet been written. I would like to get the development environment including docker configuration added to this repository when I've had a chance to clean it up.
