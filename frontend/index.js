const express = require('express');
const app = express();
const path = require('path');
const PORT = 5000;
const { exec } = require('child_process');
const axios = require('axios')
const fs = require('fs');
const crypto = require('crypto')


app.use(express.urlencoded())
app.use(express.json())
app.use(express.static(path.join(__dirname, 'public')))

app.use('/send', async (req, res) => {
    console.log("sending...")
    const form = req.body
    console.log(form)
    var pwd = form.password
    var pwd_len = pwd.length

    var pwd_hash = crypto.createHash('md5').update(pwd).digest('hex')

    var total_comb = Math.pow(26,pwd_len) //4 = 450 000

    let batch_size = 50000000
    var batches = Math.ceil(total_comb/batch_size)

    axios.post(`http://timer-service.default.svc:81/start`).catch((err)=>{
            console.log("error caught")
            console.log(new Error(err.message))
        })

    meta ={
        pwd:pwd_hash,
        length:pwd_len,
        batch_size:batch_size,
        batches: batches
    }

    axios.post("http://producer-service.default.svc:83/produce",meta).catch(err =>{
        console.log(new Error(err.message))
    })

    res.send("Breaking your unsafe password")
})

async function get_worker_count_ip(){
    console.log("called worker count")
    let ret = await new Promise((resolve, reject) => {
        exec('curl https://kubernetes.default.svc/api/v1/namespaces/default/endpoints --silent --header "Authorization: Bearer $(cat $TOKEN)" --insecure > endpoints.json',(err) =>{
            if(err){
                reject("error")
                return
            }
            resolve('endpoints')
        })
    }).then((result) =>{
        return result
    }).catch((err) =>(console.log(Error(err.message))))
    let ips = []
    let rawdata = fs.readFileSync('endpoints.json')
    let json_data = JSON.parse(rawdata)
    json_data.items.forEach(obj => {
        if(obj.hasOwnProperty('metadata')){
            if(obj.metadata.name == "worker-service"){
                obj.subsets.forEach(x =>{
                    if(x.hasOwnProperty('addresses')){
                        x.addresses.forEach(address => {
                            ips.push(address.ip)
                        })
                    }
                })
            }
        }
        });
    return ips
}

app.listen(PORT, () => console.log("listening on port changed: " + PORT));
