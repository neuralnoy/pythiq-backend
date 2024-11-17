from typing import Optional, Dict
from ..client import users_table

class UserRepository:
    async def get_by_email(self, email: str) -> Optional[Dict]:
        response = users_table.get_item(
            Key={'email': email}
        )
        return response.get('Item')

    async def create(self, user_data: Dict) -> Dict:
        users_table.put_item(Item=user_data)
        return user_data

user_repository = UserRepository()
