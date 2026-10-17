/*
    int_user_segments.sql
    
    Purpose: Classify users into segments based on their total bridge volume.
    - Whale: Users who bridged > 10 ETH total
    - Retail: Users who bridged <= 10 ETH total
    
    Business question answered: "Is this a high-value or regular user?"
    
    Note: Threshold of 10 ETH (~$25K at typical prices) separates 
    serious DeFi users from casual retail. Adjust as needed.
*/

with user_cohorts as (

    select * from {{ ref('int_user_cohorts') }}

),

segmented as (

    select
        user_address,
        cohort_month,
        first_bridge_date,
        total_bridged_eth,
        total_bridge_count,
        
        -- Segment classification
        case
            when total_bridged_eth > 10 then 'Whale'
            else 'Retail'
        end as user_segment,
        
        -- More granular tiers for deeper analysis
        case
            when total_bridged_eth > 100 then 'Mega Whale (>100 ETH)'
            when total_bridged_eth > 10 then 'Whale (10-100 ETH)'
            when total_bridged_eth > 1 then 'Mid-tier (1-10 ETH)'
            when total_bridged_eth > 0.1 then 'Retail (0.1-1 ETH)'
            else 'Micro (<0.1 ETH)'
        end as user_tier,
        
        -- Rank users by volume within their cohort
        -- it will give the rank of each user based on their total bridged eth, rank as 1 is the user with the highest total bridged eth in that cohort
        row_number() over (
            partition by cohort_month 
            order by total_bridged_eth desc
        ) as volume_rank_in_cohort

    from user_cohorts

)

select * from segmented
