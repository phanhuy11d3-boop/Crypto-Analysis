
with source as (


    select * from {{ source('linea_analytics', 'etherscan_logs') }}
    where datetime >= {{ extraction_start_utc() }}
      and datetime < {{ extraction_end_exclusive_utc() }}

),

renamed as (

    select
        -- Identifiers
        tx_hash as transaction_hash,
        block_number,
        log_index, -- index of the log in the block
        message_hash as unique_message_hash, -- we got this info extracted during transofmration process

        -- Timestamps
        datetime at time zone 'UTC' as block_timestamp,
        timestamp as block_timestamp_unix,

        -- Transaction Details
        lower(from_address) as from_address,
        lower(to_address) as to_address,
        value_eth,
        fee_eth,
        
        -- Gas / Tech details
        gas_price,
        gas_used,
        nonce,
        
        -- Metadata
        loaded_at -- when the data was loaded into the database

    from source

)

select * from renamed
