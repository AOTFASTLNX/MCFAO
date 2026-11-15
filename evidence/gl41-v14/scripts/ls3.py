import asyncio
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.house_arrest import HouseArrestService
async def main():
    async with await create_using_usbmux(connection_type="USB", autopair=False) as phone:
        async with await HouseArrestService.create(phone, "app.perseus4004.sunset349") as afc:
            for p in ("/Documents", "/Documents/game", "/Documents/game/saves"):
                try:
                    print(p, sorted(await afc.listdir(p))[:10])
                except Exception as exc:
                    print(p, type(exc).__name__)
asyncio.run(main())
