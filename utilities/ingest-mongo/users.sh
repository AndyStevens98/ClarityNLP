mongo -- "$MONGO_INITDB_DATABASE" <<EOF
var user = '$MONGO_INITDB_ROOT_USERNAME';
var passwd = '$MONGO_INITDB_ROOT_PASSWORD';
var admin = db.getSiblingDB('admin');
admin.auth(user, passwd);
db.createUser({user: user, pwd: passwd, roles: ["dbOwner"]});
use $SMARTHUB_MONGO_DATABASE;
db.createUser({ user: "$SMARTHUB_MONGO_USERNAME", pwd: "$SMARTHUB_MONGO_PASSWORD", roles: [ { role: "readWrite", db: "$SMARTHUB_MONGO_DATABASE" } ]});
EOF
