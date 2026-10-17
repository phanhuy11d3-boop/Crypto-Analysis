/*
    int_user_cohorts.sql
    
    Purpose: Assign each user to their cohort based on their FIRST bridge deposit.
    A cohort = the month when a user first bridged from Ethereum to Linea.
    
    Business question answered: "When did each user first arrive?"
*/

with bridge_deposits as (

    select * from {{ ref('stg_etherscan_logs') }}
    where value_eth > 0

),

user_first_bridge as (

    select
        from_address as user_address,
        
        -- First bridge date determines the cohort
        min(block_timestamp) as first_bridge_timestamp,
        date(min(block_timestamp)) as first_bridge_date,
        
        -- Cohort month in YYYY-MM format
        to_char(min(block_timestamp), 'YYYY-MM') as cohort_month,
        
        -- Additional context
        count(*) as total_bridge_count,
        sum(value_eth) as total_bridged_eth

    from bridge_deposits
    group by from_address

)

select
    user_address,
    first_bridge_timestamp,
    first_bridge_date,
    cohort_month,
    total_bridge_count,
    total_bridged_eth

from user_first_bridge
