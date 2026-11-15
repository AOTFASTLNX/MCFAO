import asyncio, sys
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.house_arrest import HouseArrestService
async def main():
    path = sys.argv[1]
    async with await create_using_usbmux(connection_type="USB", autopair=False) as phone:
        async with await HouseArrestService.create(phone, "app.perseus4004.sunset349") as afc:
            await afc.mkdir(path)
            print("created", path)
asyncio.run(main())
